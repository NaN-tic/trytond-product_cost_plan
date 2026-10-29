"""Remove obsolete columns from product_cost_plan_cost_type if they exist.

Run after updating product_cost_plan and its active extensions::

    trytond-console -c <config> -d <database> \
        --file update/migrate_plan_cost_types.py

If legacy plan costs need migrating, run migrate_plan_costs.py first:
it still reads plan_field_name. This cleanup can be run more than once.
"""

from trytond.pool import Pool
from trytond.transaction import Transaction


pool = Pool()
CostType = pool.get('product.cost.plan.cost.type')
table = CostType.__table_handler__()

for column in ('system', 'plan_field_name', 'minimum_percent'):
    if table.column_exist(column):
        table.drop_column(column)

Transaction().commit()
