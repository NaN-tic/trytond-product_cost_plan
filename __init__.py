#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from .plan import *
from .configuration import *

def register():
    Pool.register(
        Plan,
        PlanBOM,
        PlanProductLine,
        PlanCostType,
        PlanCost,
        Configuration,
        module='product_cost_plan', type_='model')
