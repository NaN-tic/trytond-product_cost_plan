import unittest
from decimal import Decimal

from proteus import Model, Wizard
from trytond.modules.company.tests.tools import create_company, get_company
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

        # Imports

        # Install product_cost_plan Module
        config = activate_modules('product_cost_plan')

        # Create company
        _ = create_company()
        company = get_company()
        tax_identifier = company.party.identifiers.new()
        tax_identifier.type = 'eu_vat'
        tax_identifier.code = 'BE0897290877'
        company.party.save()

        # Reload the context
        User = Model.get('res.user')
        config._context = User.get_preferences(True, config.context)

        # Create product
        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'product'
        template.producible = True
        template.default_uom = unit
        template.type = 'goods'
        template.list_price = Decimal(30)
        template.save()
        product, = template.products
        product.cost_price = Decimal(20)
        product.save()
        template = ProductTemplate()
        template.name = 'product 2'
        template.producible = True
        template.default_uom = unit
        template.type = 'goods'
        template.list_price = Decimal(30)
        template.cost_price = Decimal(0)
        template.save()
        product2, = template.products
        template = ProductTemplate()
        template.name = 'product 3'
        template.producible = True
        template.default_uom = unit
        template.type = 'goods'
        template.list_price = Decimal(15)
        template.cost_price = Decimal(0)
        template.save()
        product3, = template.products

        # Create Components
        meter, = ProductUom.find([('name', '=', 'Meter')])
        centimeter, = ProductUom.find([('symbol', '=', 'cm')])
        templateA = ProductTemplate()
        templateA.name = 'component A'
        templateA.default_uom = meter
        templateA.type = 'goods'
        templateA.list_price = Decimal(2)
        templateA.save()
        componentA, = templateA.products
        componentA.cost_price = Decimal(1)
        componentA.save()
        templateB = ProductTemplate()
        templateB.name = 'component B'
        templateB.default_uom = meter
        templateB.type = 'goods'
        templateB.list_price = Decimal(2)
        templateB.save()
        componentB, = templateB.products
        componentB.cost_price = Decimal(1)
        componentB.save()
        template1 = ProductTemplate()
        template1.name = 'component 1'
        template1.default_uom = meter
        template1.producible = True
        template1.type = 'goods'
        template1.list_price = Decimal(5)
        template1.save()
        component1, = template1.products
        component1.cost_price = Decimal(2)
        component1.save()
        template2 = ProductTemplate()
        template2.name = 'component 2'
        template2.default_uom = meter
        template2.type = 'goods'
        template2.list_price = Decimal(7)
        template2.save()
        component2, = template2.products
        component2.cost_price = Decimal(5)
        component2.save()

        # Create Bill of Material
        BOM = Model.get('production.bom')
        component_bom = BOM(name='component1')
        input1 = component_bom.inputs.new()
        input1.product = componentA
        input1.quantity = 1
        input2 = component_bom.inputs.new()
        input2.product = componentB
        input2.quantity = 1
        output = component_bom.outputs.new()
        output.product = component1
        output.quantity = 1
        component_bom.save()
        ProductBom = Model.get('product.product-production.bom')
        component1.boms.append(ProductBom(bom=component_bom))
        component1.save()
        bom = BOM(name='product')
        input1 = bom.inputs.new()
        input1.product = component1
        input1.quantity = 5
        input2 = bom.inputs.new()
        input2.product = component2
        input2.quantity = 150
        input2.uom = centimeter
        output = bom.outputs.new()
        output.product = product
        output.quantity = 1
        bom.save()
        ProductBom = Model.get('product.product-production.bom')
        product.boms.append(ProductBom(bom=bom))
        product.save()

        # Create a cost plan from BoM without child BoMs
        CostPlan = Model.get('product.cost.plan')
        plan = CostPlan()
        plan.number = '1'
        plan.product = product
        self.assertEqual(plan.bom, bom)
        plan.quantity = 1
        plan.save()
        plan.click('compute')
        plan.reload()
        self.assertEqual(len(plan.products), 2)
        c1, = plan.products.find([
            ('product', '=', component1.id),
        ], limit=1)
        self.assertEqual(c1.quantity, 5.0)
        c2, = plan.products.find([
            ('product', '=', component2.id),
        ], limit=1)
        self.assertEqual(c2.quantity, 150.0)
        cA = plan.products.find([
            ('product', '=', componentA.id),
        ], limit=1)
        self.assertEqual(len(cA), 0)
        cB = plan.products.find([
            ('product', '=', componentB.id),
        ], limit=1)
        self.assertEqual(len(cB), 0)
        cost, = plan.costs
        self.assertEqual(cost.rec_name, 'Raw materials')
        self.assertEqual(plan.cost_price, Decimal('17.5'))
        self.assertEqual(cost.cost, Decimal('17.5'))

        # Create a manual cost and test total cost is updated
        CostType = Model.get('product.cost.plan.cost.type')
        Cost = Model.get('product.cost.plan.cost')
        costtype = CostType(name='Manual')
        costtype.save()
        cost = Cost()
        cost.type = costtype
        cost.cost = Decimal('25.0')
        plan.costs.append(cost)
        plan.save()
        plan.reload()
        self.assertEqual(plan.cost_price, Decimal('42.5000'))

        # Duplicate cost plan and change plan's product
        plan2_id, = CostPlan.copy([plan.id], config.context)
        plan2 = CostPlan(plan2_id)
        self.assertEqual(plan2.bom, None)
        plan2.product = product2
        plan2.save()
        self.assertEqual(len(plan2.products), 2)

        # Update product's cost price
        self.assertEqual(plan2.cost_price, Decimal('42.5000'))
        self.assertEqual(product2.template.cost_price, Decimal('0'))
        plan2.click('update_product_cost_price')
        product2.reload()
        self.assertEqual(product2.template.cost_price, Decimal('42.5000'))

        # Create BoM from cost plan
        create_bom = Wizard('product.cost.plan.create_bom', [plan2])
        create_bom.execute('bom')
        plan2.reload()
        self.assertNotEqual(plan2.bom, None)
        self.assertNotEqual(plan2.bom, bom)
        product2.reload()
        self.assertEqual(len(product2.boms), 1)
        self.assertEqual(product2.boms[0].bom, plan2.bom)
        self.assertEqual(len(plan2.bom.inputs), 2)
        self.assertEqual(
            sorted([(i.quantity, i.product.rec_name, i.uom.symbol)
                    for i in plan2.bom.inputs]), [(5.0, 'component 1', 'm'),
                                                  (150.0, 'component 2', 'cm')])
        self.assertEqual(len(plan2.bom.outputs), 1)
        self.assertEqual(plan2.bom.outputs[0].product, product2)
        self.assertEqual(plan2.bom.outputs[0].uom, plan2.uom)
        self.assertEqual(plan2.bom.outputs[0].quantity, plan2.quantity)

        # Create plan from scratch
        plan3 = CostPlan()
        plan3.product = product3
        self.assertEqual(plan3.uom.symbol, 'u')
        plan3.bom
        plan3.quantity = 2
        plan3.click('compute')
        plan3.reload()
        self.assertEqual(len(plan3.products), 0)
        self.assertEqual(len(plan3.costs), 1)
        product_line = plan3.products.new()
        product_line.product = component1
        self.assertEqual(product_line.cost_price, Decimal('2.0000'))
        product_line.quantity = 14
        self.assertEqual(product_line.uom.symbol, 'm')
        product_line2 = product_line.children.new()
        product_line2.product = component2
        self.assertEqual(product_line2.cost_price, Decimal('5.0000'))
        product_line2.quantity = 4
        self.assertEqual(product_line2.uom.symbol, 'm')
        product_line2.uom = centimeter
        self.assertEqual(product_line2.cost_price, Decimal('0.0500'))
        product_line2.cost_price = Decimal('0.0450')
        self.assertEqual(product_line2.uom.symbol, 'cm')
        plan3.save()
        product_line, = plan3.products
        self.assertEqual(product_line.unit_cost, Decimal('14.0000'))
        self.assertEqual(product_line.total_cost, Decimal('28.0000'))
        product_line2, = product_line.children
        self.assertEqual(product_line2.unit_cost, Decimal('1.2600'))
        self.assertEqual(product_line2.total_cost, Decimal('2.5200'))
        cost, = plan3.costs
        self.assertEqual(cost.rec_name, 'Raw materials')
        self.assertEqual(cost.cost, Decimal('15.2600'))
        self.assertEqual(plan3.cost_price, Decimal('15.2600'))

        # Create BoM from Cost Plan
        create_bom = Wizard('product.cost.plan.create_bom', [plan3])
        create_bom.execute('bom')
        plan3.reload()
        product3.reload()
        self.assertEqual(plan3.bom, product3.boms[0].bom)
        self.assertEqual(len(plan3.bom.inputs), 2)
        self.assertEqual(
            sorted([(i.quantity, i.product.rec_name, i.uom.symbol)
                    for i in plan3.bom.inputs]), [(14.0, 'component 1', 'm'),
                                                  (56.0, 'component 2', 'cm')])
        self.assertEqual(len(plan3.bom.outputs), 1)
        self.assertEqual(plan3.bom.outputs[0].product, product3)
        self.assertEqual(plan3.bom.outputs[0].quantity, 2.0)
