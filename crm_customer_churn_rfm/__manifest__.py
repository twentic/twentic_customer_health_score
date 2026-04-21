{
    'name': 'CRM Customer Churn RFM',
    'version': '18.0.1.0.0',
    'author': 'TwenTIC',
    'website': 'https://www.twentic.com',
    'summary': 'Prevent customer churn using RFM (Recency, Frequency, Monetary) analysis',
    'description': """
        Extends res.partner with RFM health score fields and a daily cron job
        that detects at-risk customers based on their purchase behaviour.
        Creates automatic follow-up activities for the assigned salesperson
        when a customer's score drops below 40%.
    """,
    'category': 'Sales/CRM',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'sale',
    ],
    'data': [
        'data/ir_cron.xml',
        'views/res_partner_views.xml',
    ],
    'images': ['static/description/main_screenshot.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
