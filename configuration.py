# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.model import fields, ModelSQL
from trytond.pyson import Eval, Id
from trytond.pool import PoolMeta, Pool
from trytond.modules.company.model import CompanyValueMixin

__all__ = ['Configuration', 'ConfigurationProductcostPlan']


class Configuration(metaclass=PoolMeta):
    __name__ = 'production.configuration'
    product_cost_plan_sequence = fields.MultiValue(
        fields.Many2One('ir.sequence', "Product Cost Plan Sequence", required=True,
            domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('sequence_type', '=', Id('product_cost_plan',
                        'sequence_type_product_cost_plan')),
                ]))

    @classmethod
    def multivalue_model(cls, field):
        pool = Pool()
        if field in {'product_cost_plan_sequence'}:
            return pool.get('production.configuration.cost_plan')
        return super(Configuration, cls).multivalue_model(field)

    @classmethod
    def default_product_cost_plan_sequence(cls, **pattern):
        return cls.multivalue_model(
            'product_cost_plan_sequence').default_product_cost_plan_sequence()


class ConfigurationProductcostPlan(ModelSQL, CompanyValueMixin):
    "Production Configuration Cost Plan"
    __name__ = 'production.configuration.cost_plan'
    product_cost_plan_sequence = fields.Many2One('ir.sequence',
        "Product Cost Plan Sequence", required=True,
        domain=[
            ('company', 'in', [Eval('company', -1), None]),
            ('sequence_type', '=', Id('product_cost_plan',
                    'sequence_type_product_cost_plan')),
            ])

    @classmethod
    def default_product_cost_plan_sequence(cls):
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        try:
            return ModelData.get_id('product_cost_plan',
                'sequence_product_cost_plan')
        except KeyError:
            return None
