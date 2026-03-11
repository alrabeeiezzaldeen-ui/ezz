# -*- coding: utf-8 -*-
{
    'name': 'Multi Disbursement Voucher',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Manage multiple disbursement vouchers with automatic journal entries',
    'description': """
Multi Disbursement Voucher
===========================
This module allows you to:
* Create disbursement vouchers with multiple lines
* Disburse different amounts to multiple accounts and partners
* Automatically generate accounting entries upon posting
* Track disbursements under Accounting - Customers menu
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': ['account', 'analytic'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/multi_disbursement_voucher_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
