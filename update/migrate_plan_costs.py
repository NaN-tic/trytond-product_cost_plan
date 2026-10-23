"""Migrate the removed product.cost.plan.cost model.

Run once, after updating product_cost_plan and its active extensions::

    trytond-console -c <config> -d <database> \
        --file update/migrate_plan_costs.py

The old product_cost_plan_cost table and the system/plan_field_name columns
of product_cost_plan_cost_type must still exist. The active extensions must
no longer register product.cost.plan.cost (including product_cost_plan_margin).

Manual costs retain their type and internal_cost, without applying a margin.
The legacy records are preserved. Running this script again would duplicate
the additional costs. All changes are committed together at the end.
"""

from decimal import Decimal

from sql import Table

from trytond import backend
from trytond.pool import Pool
from trytond.transaction import Transaction


def migrate_costs():
    pool = Pool()
    Plan = pool.get('product.cost.plan')
    CostType = pool.get('product.cost.plan.cost.type')
    AdditionalCost = pool.get('product.cost.plan.additional_cost')

    transaction = Transaction()
    cursor = transaction.connection.cursor()
    legacy_cost = Table('product_cost_plan_cost')
    cost_type = CostType.__table__()
    plan = Plan.__table__()

    if not backend.TableHandler.table_exist(legacy_cost._name):
        raise RuntimeError('Legacy table product_cost_plan_cost is missing.')

    cursor.execute(*legacy_cost.join(
            cost_type, type_='LEFT',
            condition=legacy_cost.type == cost_type.id).join(
            plan, type_='LEFT',
            condition=legacy_cost.plan == plan.id).select(
                legacy_cost.id,
                legacy_cost.plan,
                cost_type.id,
                legacy_cost.system,
                cost_type.plan_field_name,
                legacy_cost.margin_percent,
                legacy_cost.internal_cost,
                plan.id,
                order_by=[legacy_cost.plan, legacy_cost.id]))
    rows = cursor.fetchall()

    margin_fields = {
        'products_cost': 'products_cost_margin',
        'operations_cost': 'operations_cost_margin',
        }
    margins = {}
    additional_costs = []
    # Validate every source line before writing anything.
    for (cost_id, plan_id, type_id, system, field_name, margin, cost,
            existing_plan_id) in rows:
        if existing_plan_id is None or type_id is None:
            raise RuntimeError(
                'Legacy cost %s has a missing plan or cost type.' % cost_id)
        if system:
            if field_name not in margin_fields:
                raise RuntimeError(
                    'Unsupported system cost %s: %s.' % (cost_id, field_name))
            target_field = margin_fields[field_name]
            if target_field not in Plan._fields:
                raise RuntimeError('Missing plan field: %s.' % target_field)
            values = margins.setdefault(plan_id, {})
            margin = float(margin or 0)
            if target_field in values and values[target_field] != margin:
                raise RuntimeError(
                    'Conflicting %s values on plan %s.'
                    % (target_field, plan_id))
            # Tryton stores percentages as fractions in both models.
            values[target_field] = margin
        else:
            additional_costs.append({
                    'plan': plan_id,
                    'type': type_id,
                    'calculation': 'fixed',
                    'cost': cost if cost is not None else Decimal(0),
                    })

    for plan_id, values in margins.items():
        Plan.write([Plan(plan_id)], values)
    if additional_costs:
        AdditionalCost.create(additional_costs)

    transaction.commit()
    print('Migrated margins on %s plans; created %s fixed additional costs.'
        % (len(margins), len(additional_costs)))


migrate_costs()
