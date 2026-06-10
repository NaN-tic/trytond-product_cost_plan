import unittest
from datetime import timedelta
from decimal import Decimal

from proteus import Model, Wizard
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.exceptions import UserError, UserWarning
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        def setup_step_line_routing_cache(config=None):
            return None

        config = activate_modules(
            ['product_cost_plan', 'production_plan'],
            setup_step_line_routing_cache)

        _ = create_company()
        company = get_company()
        tax_identifier = company.party.identifiers.new()
        tax_identifier.type = 'eu_vat'
        tax_identifier.code = 'BE0897290877'
        company.party.save()

        User = Model.get('res.user')
        config._context = User.get_preferences(True, config.context)

        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])

        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'product'
        template.producible = True
        template.default_uom = unit
        template.type = 'goods'
        template.list_price = Decimal('30')
        template.save()
        product, = template.products

        WorkCenterCategory = Model.get('production.work.center.category')
        category = WorkCenterCategory(name='Assembly')
        category.save()
        other_category = WorkCenterCategory(name='Packaging')
        other_category.save()

        WorkCenter = Model.get('production.work.center')
        root_center = WorkCenter(name='Root')
        root_center.save()
        cycle_center = WorkCenter(name='Cycle Center')
        cycle_center.parent = root_center
        cycle_center.category = category
        cycle_center.cost_price = Decimal('30')
        cycle_center.cost_method = 'cycle'
        cycle_center.save()
        hour_center = WorkCenter(name='Hour Center')
        hour_center.parent = root_center
        hour_center.category = category
        hour_center.cost_price = Decimal('15')
        hour_center.cost_method = 'hour'
        hour_center.save()

        Operation = Model.get('production.routing.operation')
        assembly_operation = Operation(name='Assembly Operation')
        assembly_operation.work_center_category = category
        assembly_operation.save()
        packaging_operation = Operation(name='Packaging Operation')
        packaging_operation.work_center_category = other_category
        packaging_operation.save()

        CostPlan = Model.get('product.cost.plan')
        Warning = Model.get('res.user.warning')
        plan = CostPlan()
        plan.product = product
        plan.quantity = 10
        plan.save()

        operation = plan.operations.new()
        operation.name = 'Assembly'
        operation.work_center = cycle_center
        self.assertEqual(operation.work_center_category, category)
        self.assertEqual(operation.cost_price, Decimal('30'))
        self.assertEqual(operation.cost_method, 'cycle')
        operation.operation = assembly_operation
        self.assertEqual(operation.work_center_category, category)
        operation.time = timedelta(hours=2)
        operation.quantity = 5
        operation = plan.operations.new()
        operation.name = 'Finishing'
        operation.work_center = hour_center
        self.assertEqual(operation.work_center_category, category)
        self.assertEqual(operation.cost_price, Decimal('15'))
        self.assertEqual(operation.cost_method, 'hour')
        operation.operation = assembly_operation
        operation.time = timedelta(hours=2)
        operation.calculation = 'fixed'
        plan.save()
        plan.reload()

        cycle_operation, hour_operation = plan.operations
        self.assertEqual(cycle_operation.total_cost, Decimal('60.00'))
        self.assertEqual(cycle_operation.unit_cost, Decimal('6.00'))
        self.assertEqual(hour_operation.total_cost, Decimal('30.00'))
        self.assertEqual(hour_operation.unit_cost, Decimal('3.00'))

        plan.click('compute')
        plan.reload()
        self.assertEqual(plan.operations_cost, Decimal('9.00'))
        self.assertEqual(plan.cost_price, Decimal('9.0000'))
        operations_cost, = plan.costs.find([
            ('type.name', '=', 'Operations'),
        ], limit=1)
        self.assertEqual(operations_cost.cost, Decimal('9.0000'))

        plan2 = CostPlan()
        plan2.product = product
        plan2.quantity = 4
        plan2.save()
        operation2 = plan2.operations.new()
        operation2.name = 'Packing'
        self.assertEqual(operation2.cost_method, 'hour')
        operation2.cost_method = 'cycle'
        operation2.cost_price = Decimal('45')
        operation2.work_center = hour_center
        self.assertEqual(operation2.cost_method, 'hour')
        self.assertEqual(operation2.cost_price, Decimal('45'))
        operation2.time = timedelta(hours=1, minutes=30)
        operation2.quantity = 2

        operation3 = plan2.operations.new()
        operation3.name = 'Manual'
        self.assertEqual(operation3.cost_method, 'hour')
        operation3.cost_method = 'cycle'
        self.assertEqual(operation3.cost_method, 'cycle')
        operation3.cost_price = Decimal('20')
        operation3.operation = assembly_operation
        operation3.time = timedelta(minutes=30)
        operation3.calculation = 'fixed'
        plan2.save()

        create_bom = Wizard('product.cost.plan.create_bom', [plan2])
        with self.assertRaises(UserError):
            create_bom.execute('bom')

        plan2.reload()
        operation2, operation3 = plan2.operations
        operation2.operation = packaging_operation
        plan2.save()

        create_bom = Wizard('product.cost.plan.create_bom', [plan2])
        create_bom.execute('bom')
        plan2.reload()
        self.assertEqual(len(plan2.bom.routings), 1)
        routing, = plan2.bom.routings
        self.assertEqual(plan2.product.boms[0].routing, routing)
        self.assertEqual(routing.name, plan2.rec_name)
        self.assertEqual(len(routing.steps), 2)
        self.assertEqual(routing.steps[0].operation, packaging_operation)
        self.assertEqual(routing.steps[0].calculation, 'standard')
        self.assertEqual(routing.steps[0].time, timedelta(hours=1.5))
        self.assertEqual(routing.steps[1].operation, assembly_operation)
        self.assertEqual(routing.steps[1].calculation, 'fixed')
        self.assertEqual(routing.steps[1].time, timedelta(minutes=30))

        plan3 = CostPlan()
        plan3.product = product
        plan3.quantity = 8
        plan3.save()
        operation4 = plan3.operations.new()
        operation4.name = 'Second BOM Step'
        operation4.operation = assembly_operation
        operation4.time = timedelta(hours=1)
        operation4.cost_price = Decimal('10')
        operation4.quantity = 4
        plan3.save()

        create_bom = Wizard('product.cost.plan.create_bom', [plan3])
        while True:
            try:
                create_bom.execute('bom')
                break
            except UserWarning as warning:
                _, (key, *_) = warning.args
                Warning(user=config.user, name=key, always=True).save()
        plan3.reload()
        self.assertEqual(plan3.product.boms[0].bom, plan3.bom)
        self.assertEqual(plan3.product.boms[0].routing, plan3.bom.routings[0])
