"""Remove obsolete cost types and columns if they exist.

Run after updating product_cost_plan and its active extensions::

    trytond-console -c <config> -d <database> \
        --file update/migrate_plan_cost_types.py

Run migrate_plan_costs.py first if the legacy cost table exists: it still
reads plan_field_name and drops the table after migrating its records.
This cleanup refuses to run while that table exists or obsolete types are
used by additional costs. This cleanup can be run more than once.
"""

from trytond import backend
from trytond.pool import Pool
from trytond.transaction import Transaction


pool = Pool()
CostType = pool.get('product.cost.plan.cost.type')
AdditionalCost = pool.get('product.cost.plan.additional_cost')

if backend.TableHandler.table_exist('product_cost_plan_cost'):
    raise RuntimeError(
        'Run migrate_plan_costs.py before removing obsolete cost types: '
        'product_cost_plan_cost still exists.')

with Transaction().set_context(language='en'):
    cost_types = CostType.search([
            ('name', 'in', ['Raw materials', 'Operations']),
            ])
    if cost_types:
        if AdditionalCost.search([
                    ('type', 'in', [cost_type.id for cost_type in cost_types]),
                    ], limit=1):
            raise RuntimeError(
                'Cannot remove obsolete cost types: '
                'they are still used by additional costs.')
        CostType.delete(cost_types)

table = CostType.__table_handler__()

for column in ('system', 'plan_field_name', 'minimum_percent'):
    if table.column_exist(column):
        table.drop_column(column)

Transaction().commit()
