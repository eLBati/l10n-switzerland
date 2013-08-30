# -*- encoding: utf-8 -*-
##############################################################################
#
#    Author: Nicolas Bessi. Copyright Camptocamp SA
#    Donors: Hasa Sàrl, Open Net Sàrl and Prisme Solutions Informatique SA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from datetime import datetime
from osv import fields, osv
from tools import mod10r

class account_invoice(osv.osv):
    """Inherit account.invoice in order to add bvr
    printing functionnalites. BVR is a Swiss payment vector"""
    _inherit = "account.invoice"

    ## @param self The object pointer.
    ## @param cursor a psycopg cursor
    ## @param user res.user.id that is currently loged
    ## @parma context a standard dict
    ## @return a list of tuple (name,value)
    def _get_reference_type(self, cursor, user, context=None):
        """Function use by the function field reference_type in order to initalise available
        BVR Reference Types"""
        res = super(account_invoice, self)._get_reference_type(cursor, user,
                context=context)
        res.append(('bvr', 'BVR'))
        return res

    ## @param self The object pointer.
    ## @param cursor a psycopg cursor
    ## @param user res.user.id that is currently loged
    ## @parma context a standard dict
    ## @param name of the files
    ## @param args a list of diverse argument
    ## @parma context a standard dict
    ## @return a  dict (invoice id,amount to pay)
    def _amount_to_pay(self, cursor, user, ids, name, args, context=None):
        '''Return the amount still to pay regarding all the payment orders'''
        if not ids:
            return {}
        res = {}
        for invoice in self.browse(cursor, user, ids, context=context):
            res[invoice.id] = 0.0
            if invoice.move_id:
                for line in invoice.move_id.line_id:
                    if not line.date_maturity or \
                            datetime.strptime(line.date_maturity, '%Y-%m-%d') \
                            < datetime.now():
                        res[invoice.id] += line.amount_to_pay
        return res

    _columns = {
        ### BVR reference type BVR or FREE
        'reference_type': fields.selection(_get_reference_type,
            'Reference Type', required=True),
        ### Partner bank link between bank and partner id
        'partner_bank_id': fields.many2one('res.partner.bank', 'Bank Account',
            help='The partner bank account to pay\nKeep empty to use the default'
            ),
        ### Amount to pay
        'amount_to_pay': fields.function(_amount_to_pay,
            type='float', 
            string='Amount to be paid',
            help='The amount which should be paid at the current date\n' \
                    'minus the amount which is already in payment order'),
        'text_condition1': fields.many2one('account.condition_text', 'Invoice information Top'),
        'text_condition2': fields.many2one('account.condition_text', 'Invoice information Bottom'),
        'note1' : fields.text('Invoice information Top'),
        'note2' : fields.text('Invoice information Bottom'),
    }

    ## @param self The object pointer.
    ## @param cursor a psycopg cursor
    ## @param user res.user.id that is currently loged
    ## @parma ids invoices id
    ## @return a boolean True if valid False if invalid
    def _check_bvr(self, cr, uid, ids, context=None):
        """
        Function to validate a bvr reference like :
        0100054150009>132000000000000000000000014+ 1300132412>
        The validation is based on l10n_ch
        """
        invoices = self.browse(cr,uid,ids)
        for invoice in invoices:
            if invoice.reference_type == 'bvr':
                if not invoice.reference:
                    return False
                ## I need help for this bug because in this case
                # <010001000060190> 052550152684006+ 43435>
                # the reference 052550152684006 do not match modulo 10
                #
                if mod10r(invoice.reference[:-1]) != invoice.reference and \
                    len(invoice.reference) == 15:
                    return True
                #
                if mod10r(invoice.reference[:-1]) != invoice.reference:
                    return False
        return True
    ## @param self The object pointer.
    ## @param cursor a psycopg cursor
    ## @param user res.user.id that is currently loged
    ## @parma ids invoices id
    ## @return a boolean True if valid False if invalid
    def _check_reference_type(self, cursor, user, ids, context=None):
        """Check the customer invoice reference type depending
        on the BVR reference type and the invoice partner bank type"""
        for invoice in self.browse(cursor, user, ids):
            if invoice.type in 'in_invoice':
                if invoice.partner_bank_id and \
                        invoice.partner_bank_id.state in \
                        ('bvrbank', 'bvrpost') and \
                        invoice.reference_type != 'bvr':
                    return False
        return True

    _constraints = [
        (_check_bvr, 'Error: Invalid Bvr Number (wrong checksum).',
            ['reference']),
        (_check_reference_type, 'Error: BVR reference is required.',
            ['reference_type']),
    ]

    ## @param self The object pointer.
    ## @param cr a psycopg cursor
    ## @param uid res.user.id that is currently loged
    ## @parma ids invoices id
    ## @parma type the invoice type
    ## @param partner_id the partner linked to the invoice
    ## @parma date_invoice date of the invoice
    ## @parma payment_term inoice payment term
    ## @param partner_bank_id the partner linked invoice bank
    ## @return the dict of values with the partner_bank value updated
    def onchange_partner_id(self, cr, uid, ids, type, partner_id,
            date_invoice=False, payment_term=False, partner_bank_id=False, company_id=False):
        """ Function that is call when the partner of the invoice is changed
        it will retrieve and set the good bank partner bank"""
        #context not define in signature of function in account module
        context = {}
        res = super(account_invoice, self).onchange_partner_id(cr,
                                                               uid,
                                                               ids,
                                                               type,
                                                               partner_id,
                                                               date_invoice,
                                                               payment_term,
                                                               partner_bank_id,
                                                               company_id)
        bank_id = False
        if partner_id:
            if type in ('in_invoice', 'in_refund'):
                p = self.pool.get('res.partner').browse(cr, uid, partner_id, context)
                if p.bank_ids:
                    bank_id = p.bank_ids[0].id
                res['value']['partner_bank_id'] = bank_id
            else:
                user = self.pool.get('res.users').browse(cr, uid, uid, context)
                bank_ids = user.company_id.partner_id.bank_ids
                if bank_ids:
                    #How to order bank ?
                    for bank in bank_ids:
                        if bank.my_bank:
                            bank_id = bank.id
                res['value']['partner_bank_id'] = bank_id

        if partner_bank_id != bank_id:
            to_update = self.onchange_partner_bank(cr, uid, ids, bank_id)
            res['value'].update(to_update['value'])
        return res

    ## @param self The object pointer.
    ## @param cursor a psycopg cursor
    ## @param user res.user.id that is currently loged
    ## @parma ids invoices id
    ## @param partner_bank_id the partner linked invoice bank
    ## @return the dict of values with the reference type  value updated
    def onchange_partner_bank(self, cursor, user, ids, partner_bank_id):
        """update the reference type depending of the partner bank"""
        res = {'value': {}}
        partner_bank_obj = self.pool.get('res.partner.bank')
        if partner_bank_id:
            partner_bank = partner_bank_obj.browse(cursor, user, partner_bank_id)
            if partner_bank.state in ('bvrbank', 'bvrpost'):
                res['value']['reference_type'] = 'bvr'
        return res

    def get_trans(self, cr, uid, name, res_id, lang) :
        sql = " SELECT value     from ir_translation where name = '%s' \
        and res_id = %s and lang ='%s';" %(name, str(res_id), lang)
        cr.execute(sql)
        toreturn =  cr.fetchone()
        if toreturn :
         return toreturn[0]
        else :
            return toreturn
        
    def set_comment(self, cr,uid,id,commentid):
        if not commentid :
            return {}
        cond = self.pool.get('account.condition_text').browse(
            cr,uid,commentid,{})
        translation_obj = self.pool.get('ir.translation')
        

        text =''
        if cond :
            text = cond.text
            try :
                lang = self.browse(cr, uid, id)[0].partner_id.lang
            except :
                lang = 'en_EN'
            res_trans = self.get_trans(cr, uid, 'account.condition_text,text', commentid, lang )
            if not res_trans :
                res_trans = text
        
        return {'value': {
                'note1': res_trans,
                }}
                
                
    def set_note(self, cr,uid,id,commentid):
        if not commentid :
            return {}
        cond = self.pool.get('account.condition_text').browse(
            cr,uid,commentid,{})
        translation_obj = self.pool.get('ir.translation')
        

        text =''
        if cond :
            text = cond.text
            try :
                lang = self.browse(cr, uid, id)[0].partner_id.lang
            except :
                lang = 'en_EN'
            res_trans = self.get_trans(cr, uid, 
                'account.condition_text,text', commentid, lang )
            if not res_trans :
                res_trans = text
        
        return {'value': {
                'note2': res_trans,
                }}




account_invoice()

class account_tax_code(osv.osv):
    """Inherit account tax code in order
    to add a Case code"""
    _name = 'account.tax.code'
    _inherit = "account.tax.code"
    _columns = {
        'code': fields.char('Case Code', size=512),
    }

account_tax_code()

class invoice_condition_text(osv.osv):
    """add info condition in the invoice"""
    _name = "account.condition_text"
    _description = "Invoice condition text"
    
        
    _columns = {
        'name' : fields.char('Methode', required=True, size=128),
        'type' : fields.selection([('header','Header'),
        ('footer','Footer')
        ], 
        'type',required=True),
        'text': fields.text('text', translate=True,required=True),
    }

        
invoice_condition_text()


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: