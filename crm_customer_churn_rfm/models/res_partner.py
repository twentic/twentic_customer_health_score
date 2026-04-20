import logging
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Thresholds
SCORE_AT_RISK = 40.0       # Below this → create activity
SCORE_HEALTHY = 70.0       # Above this → green
MIN_INVOICES = 3           # Minimum invoices required to compute a score


class ResPartner(models.Model):
    _inherit = 'res.partner'

    rfm_score = fields.Float(
        string='RFM Health Score (%)',
        digits=(5, 2),
        default=0.0,
        help=(
            'Customer health score calculated from RFM analysis (0–100 %). '
            'Green ≥ 70 %, Orange 40–70 %, Red < 40 % (at risk).'
        ),
    )
    rfm_last_purchase_date = fields.Date(
        string='Last Purchase Date',
        readonly=True,
        help='Date of the most recent confirmed (posted) invoice.',
    )
    rfm_purchase_frequency = fields.Float(
        string='Purchase Frequency (days)',
        digits=(10, 2),
        default=0.0,
        readonly=True,
        help='Average number of days between consecutive posted invoices.',
    )

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    def _compute_rfm_score(self):
        """Compute and write RFM health scores for the current recordset.

        Partners with fewer than MIN_INVOICES posted invoices are skipped
        so that the metric is statistically meaningful.
        """
        today = date.today()
        AccountMove = self.env['account.move']
        MailActivity = self.env['mail.activity']

        # Resolve the "To-Do" activity type; fall back to the first available one
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False
        )
        if not activity_type:
            activity_type = self.env['mail.activity.type'].search([], limit=1)

        partner_model_id = self.env['ir.model']._get_id('res.partner')

        for partner in self:
            invoices = AccountMove.search(
                [
                    ('partner_id', 'child_of', partner.id),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('invoice_date', '!=', False),
                ],
                order='invoice_date asc',
            )

            if len(invoices) < MIN_INVOICES:
                _logger.debug(
                    'RFM: skipping partner %s (only %d invoices)',
                    partner.display_name,
                    len(invoices),
                )
                continue

            # --- Derived data -----------------------------------------------
            invoice_dates = invoices.mapped('invoice_date')
            invoice_amounts = invoices.mapped('amount_untaxed')

            last_purchase_date = invoice_dates[-1]

            # Average days between consecutive invoices
            if len(invoice_dates) >= 2:
                span_days = (invoice_dates[-1] - invoice_dates[0]).days
                frequency = span_days / (len(invoice_dates) - 1)
            else:
                frequency = 30.0
            frequency = max(frequency, 1.0)

            partner.rfm_last_purchase_date = last_purchase_date
            partner.rfm_purchase_frequency = frequency

            # --- Recency score (0–100) --------------------------------------
            days_since = (today - last_purchase_date).days
            if days_since <= frequency:
                recency_score = 100.0
            elif days_since <= 2.0 * frequency:
                # Linear decay 100 → 50 between 1× and 2× frequency
                recency_score = 100.0 - ((days_since - frequency) / frequency) * 50.0
            else:
                # Continues to decay towards 0 beyond 2× frequency
                recency_score = max(
                    0.0,
                    50.0 - ((days_since - 2.0 * frequency) / frequency) * 50.0,
                )

            # --- Monetary score (0–100) -------------------------------------
            overall_avg = sum(invoice_amounts) / len(invoice_amounts)
            last_two_avg = sum(invoice_amounts[-2:]) / 2

            if overall_avg > 0:
                monetary_ratio = last_two_avg / overall_avg
                monetary_score = min(100.0, max(0.0, monetary_ratio * 100.0))
            else:
                monetary_score = 100.0

            # Alert flag: last 2 orders fell ≥ 40 % below historical average
            if overall_avg > 0 and last_two_avg < (1.0 - 0.40) * overall_avg:
                _logger.info(
                    'RFM monetary alert for %s: last-2 avg %.2f vs overall avg %.2f',
                    partner.display_name,
                    last_two_avg,
                    overall_avg,
                )

            # --- Combined RFM score (60 % recency + 40 % monetary) ----------
            rfm_score = (0.6 * recency_score) + (0.4 * monetary_score)
            rfm_score = min(100.0, max(0.0, rfm_score))

            partner.rfm_score = rfm_score

            # --- Create follow-up activity if score is below threshold -------
            if rfm_score < SCORE_AT_RISK and activity_type:
                existing_activity = MailActivity.search(
                    [
                        ('res_model', '=', 'res.partner'),
                        ('res_id', '=', partner.id),
                        ('activity_type_id', '=', activity_type.id),
                        ('summary', 'ilike', 'RFM'),
                    ],
                    limit=1,
                )
                if not existing_activity:
                    salesperson = partner.user_id or self.env.user
                    MailActivity.create(
                        {
                            'res_model_id': partner_model_id,
                            'res_id': partner.id,
                            'activity_type_id': activity_type.id,
                            'summary': 'RFM Alert: At-Risk Customer',
                            'note': (
                                f'The RFM health score for <b>{partner.display_name}</b> '
                                f'has dropped to <b>{rfm_score:.1f}%</b>.<br/>'
                                f'Last purchase: {last_purchase_date}.<br/>'
                                f'Average purchase frequency: {frequency:.0f} days.<br/>'
                                f'Consider proactive contact to prevent churn.'
                            ),
                            'user_id': salesperson.id,
                            'date_deadline': today + timedelta(days=3),
                        }
                    )
                    _logger.info(
                        'RFM: created at-risk activity for %s (score %.1f%%)',
                        partner.display_name,
                        rfm_score,
                    )

    # ------------------------------------------------------------------
    # Manual trigger (button / server action)
    # ------------------------------------------------------------------

    def action_compute_rfm_score(self):
        """Manual trigger: recompute RFM scores for selected partners."""
        self._compute_rfm_score()

    # ------------------------------------------------------------------
    # Scheduled action (cron)
    # ------------------------------------------------------------------

    @api.model
    def _cron_compute_rfm_scores(self):
        """Daily cron: recompute RFM scores for all customer partners."""
        partners = self.search([('customer_rank', '>', 0)])
        _logger.info(
            'CRM Churn RFM: starting score computation for %d customers',
            len(partners),
        )
        partners._compute_rfm_score()
        _logger.info('CRM Churn RFM: score computation finished')
