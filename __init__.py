# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

from trytond.pool import Pool
from . import plan
from . import configuration
from . import production_plan


def register():
    Pool.register(
        plan.Plan,
        plan.PlanBOM,
        plan.PlanProductLine,
        plan.PlanCostType,
        plan.PlanCost,
        configuration.Configuration,
        configuration.ConfigurationProductcostPlan,
        plan.CreateBomStart,
        module='product_cost_plan', type_='model')
    Pool.register(
        production_plan.PlanOperationLine,
        production_plan.Plan,
        production_plan.ProductBom,
        module='product_cost_plan', type_='model', depends=['production_plan'])
    Pool.register(
        plan.CreateBom,
        module='product_cost_plan', type_='wizard')
