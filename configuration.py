#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import fields
from trytond.pyson import Eval
from trytond.pool import PoolMeta

__all__ = ['Configuration']
__metaclass__ = PoolMeta


class Configuration:
    __name__ = 'production.configuration'

    product_cost_plan_sequence = fields.Property(fields.Many2One('ir.sequence',
            'Product Cost Plan Sequence', domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('code', '=', 'product_cost_plan'),
                ], required=True))
