# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.model import fields, ModelSQL
from trytond.pyson import Eval
from trytond.pool import PoolMeta, Pool
from trytond.modules.company.model import (
    CompanyMultiValueMixin, CompanyValueMixin)

__all__ = ['Configuration', 'ConfigurationProductcostPlan']


class Configuration(CompanyMultiValueMixin, metaclass=PoolMeta):
    __name__ = 'production.configuration'

    product_cost_plan_sequence = fields.MultiValue(
        fields.Many2One('ir.sequence',
            'Product Cost Plan Sequence', domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('code', '=', 'product_cost_plan'),
                ], required=True))

    @classmethod
    def multivalue_model(cls, field):
        pool = Pool()
        if field in {'product_cost_plan_sequence'}:
            return pool.get('production.configuration.cost_plan')
        return super(Configuration, cls).multivalue_model(field)


class ConfigurationProductcostPlan(ModelSQL, CompanyValueMixin):
    "Production Configuration Cost Plan"
    __name__ = 'production.configuration.cost_plan'

    product_cost_plan_sequence = fields.Many2One('ir.sequence',
            'Product Cost Plan Sequence', domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('code', '=', 'product_cost_plan'),
                ], required=True)
