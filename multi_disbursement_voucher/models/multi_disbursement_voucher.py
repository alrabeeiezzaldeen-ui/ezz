from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MultiDisbursementVoucher(models.Model):
    _name = 'multi.disbursement.voucher'
    _description = 'Multi Disbursement Voucher'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Voucher Number', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, domain="[('type', 'in', ('cash', 'bank'))]")
    total_amount = fields.Monetary(string='Total Amount', compute='_compute_total_amount', store=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    general_description = fields.Text(string='General Description')
    disbursement_line_ids = fields.One2many('multi.disbursement.voucher.line', 'voucher_id', string='Disbursement Details', copy=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, default='draft', tracking=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('multi.disbursement.voucher') or _('New')
        return super(MultiDisbursementVoucher, self).create(vals)

    @api.depends("disbursement_line_ids.amount_total")
    def _compute_total_amount(self):
        for voucher in self:
            voucher.total_amount = sum(voucher.disbursement_line_ids.mapped("amount_total"))

    def action_post(self):
        self.ensure_one()
        if not self.disbursement_line_ids:
            raise ValidationError(_('You must add at least one disbursement line.'))
        if self.total_amount <= 0:
            raise ValidationError(_('The total amount must be positive.'))

        # Create journal entry
        move_lines = []

        # Credit line for Cash/Bank account
        credit_account = self.journal_id.default_account_id
        if not credit_account:
            raise ValidationError(_("The journal '%s' does not have a default account. Please configure it in the journal settings.") % self.journal_id.name)

        move_lines.append((0, 0, {
            'name': self.general_description or _('Multi Disbursement Voucher %s', self.name),
            'account_id': credit_account.id,
            'credit': self.total_amount,
            'debit': 0.0,
            'currency_id': self.currency_id.id,
            'partner_id': False,
        }))

        # Debit lines based on disbursement details
        for line in self.disbursement_line_ids:
            if not line.debit_account_id:
                raise ValidationError(_("Please specify a debit account for all disbursement lines."))
            if line.amount_untaxed <= 0:
                raise ValidationError(_("Disbursement line untaxed amount must be positive."))

            # Debit line for the untaxed amount
            move_lines.append((0, 0, {
                'name': line.description or self.general_description or _("Disbursement for %s", line.debit_account_id.name),
                'account_id': line.debit_account_id.id,
                'debit': line.amount_untaxed,
                'credit': 0.0,
                'currency_id': self.currency_id.id,
                'partner_id': line.partner_id.id,
                'analytic_distribution': {str(line.analytic_account_id.id): 100} if line.analytic_account_id else False,
            }))

            # Debit lines for taxes
            if line.tax_ids:
                taxes_results = line.tax_ids.compute_all(line.amount_untaxed, currency=self.currency_id, partner=line.partner_id)
                for tax_res in taxes_results["taxes"]:
                    move_lines.append((0, 0, {
                        'name': tax_res["name"],
                        'account_id': tax_res["account_id"],
                        'debit': tax_res["amount"],
                        'credit': 0.0,
                        'currency_id': self.currency_id.id,
                        'partner_id': line.partner_id.id,
                        'analytic_distribution': {str(line.analytic_account_id.id): 100} if line.analytic_account_id else False,
                    }))

        move_vals = {
            'ref': self.name,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'line_ids': move_lines,
            'move_type': 'entry',
        }

        move = self.env['account.move'].create(move_vals)
        move.action_post()

        self.write({
            'state': 'posted',
            'move_id': move.id,
        })
        return True

    def action_cancel(self):
        self.ensure_one()
        if self.move_id:
            self.move_id.button_draft()
            self.move_id.button_cancel()
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})


class MultiDisbursementVoucherLine(models.Model):
    _name = 'multi.disbursement.voucher.line'
    _description = 'Multi Disbursement Voucher Line'

    voucher_id = fields.Many2one('multi.disbursement.voucher', string='Disbursement Voucher', required=True, ondelete='cascade')
    debit_account_id = fields.Many2one('account.account', string='Debit Account', required=True, domain="[('deprecated', '=', False)]")
    partner_id = fields.Many2one('res.partner', string='Partner')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    description = fields.Char(string='Description')
    amount_untaxed = fields.Monetary(string='Amount (Untaxed)', required=True)
    tax_ids = fields.Many2many('account.tax', string='Taxes', domain=[('active', '=', True)])
    tax_amount = fields.Monetary(string='Tax Amount', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(string='Total Amount', compute='_compute_amounts', store=True)
    currency_id = fields.Many2one(related='voucher_id.currency_id', store=True, string='Currency', readonly=True)

    @api.depends('amount_untaxed', 'tax_ids.amount')
    def _compute_amounts(self):
        for line in self:
            taxes = line.tax_ids.compute_all(line.amount_untaxed, currency=line.currency_id, partner=line.partner_id)
            line.tax_amount = sum(t['amount'] for t in taxes['taxes'])
            line.amount_total = taxes['total_included']

    @api.constrains('amount_untaxed')
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_('The amount of a disbursement line must be positive.'))
