==========================
Product Cost Plan Scenario
==========================

=============
General Setup
=============

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import config, Model, Wizard
    >>> today = datetime.date.today()
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company

Install product_cost_plan Module::

    >>> config = activate_modules('product_cost_plan')

Create company::

    >>> _ = create_company()
    >>> company = get_company()
    >>> tax_identifier = company.party.identifiers.new()
    >>> tax_identifier.type = 'eu_vat'
    >>> tax_identifier.code = 'BE0897290877'
    >>> company.party.save()

Reload the context::

    >>> User = Model.get('res.user')
    >>> config._context = User.get_preferences(True, config.context)

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.producible = True
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal(30)
    >>> template.save()
    >>> product, = template.products
    >>> product.cost_price = Decimal(20)
    >>> product.save()

    >>> template = ProductTemplate()
    >>> template.name = 'product 2'
    >>> template.producible = True
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal(30)
    >>> template.cost_price = Decimal(0)
    >>> template.save()
    >>> product2, = template.products

    >>> template = ProductTemplate()
    >>> template.name = 'product 3'
    >>> template.producible = True
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal(15)
    >>> template.cost_price = Decimal(0)
    >>> template.save()
    >>> product3, = template.products

Create Components::

    >>> meter, = ProductUom.find([('name', '=', 'Meter')])
    >>> centimeter, = ProductUom.find([('name', '=', 'centimeter')])
    >>> templateA = ProductTemplate()
    >>> templateA.name = 'component A'
    >>> templateA.default_uom = meter
    >>> templateA.type = 'goods'
    >>> templateA.list_price = Decimal(2)
    >>> templateA.save()
    >>> componentA, = templateA.products
    >>> componentA.cost_price = Decimal(1)
    >>> componentA.save()

    >>> templateB = ProductTemplate()
    >>> templateB.name = 'component B'
    >>> templateB.default_uom = meter
    >>> templateB.type = 'goods'
    >>> templateB.list_price = Decimal(2)
    >>> templateB.save()
    >>> componentB, = templateB.products
    >>> componentB.cost_price = Decimal(1)
    >>> componentB.save()

    >>> template1 = ProductTemplate()
    >>> template1.name = 'component 1'
    >>> template1.default_uom = unit
    >>> template1.producible = True
    >>> template1.type = 'goods'
    >>> template1.list_price = Decimal(5)
    >>> template1.save()
    >>> component1, = template1.products
    >>> component1.cost_price = Decimal(2)
    >>> component1.save()

    >>> template2 = ProductTemplate()
    >>> template2.name = 'component 2'
    >>> template2.default_uom = meter
    >>> template2.type = 'goods'
    >>> template2.list_price = Decimal(7)
    >>> template2.save()
    >>> component2, = template2.products
    >>> component2.cost_price = Decimal(5)
    >>> component2.save()

Create Bill of Material::

    >>> BOM = Model.get('production.bom')
    >>> component_bom = BOM(name='component1')
    >>> input1 = component_bom.inputs.new()
    >>> input1.product = componentA
    >>> input1.quantity = 1
    >>> input2 = component_bom.inputs.new()
    >>> input2.product = componentB
    >>> input2.quantity = 1
    >>> output = component_bom.outputs.new()
    >>> output.product = component1
    >>> output.quantity = 1
    >>> component_bom.save()

    >>> ProductBom = Model.get('product.product-production.bom')
    >>> component1.boms.append(ProductBom (bom=component_bom))
    >>> component1.save()

    >>> bom = BOM(name='product')
    >>> input1 =  bom.inputs.new()
    >>> input1.product = component1
    >>> input1.quantity = 5
    >>> input2 =  bom.inputs.new()
    >>> input2.product = component2
    >>> input2.quantity = 150
    >>> input2.uom = centimeter
    >>> output = bom.outputs.new()
    >>> output.product = product
    >>> output.quantity = 1
    >>> bom.save()

    >>> ProductBom = Model.get('product.product-production.bom')
    >>> product.boms.append(ProductBom(bom=bom))
    >>> product.save()

Create a cost plan from BoM without child BoMs::

    >>> CostPlan = Model.get('product.cost.plan')
    >>> plan = CostPlan()
    >>> plan.number = '1'
    >>> plan.product = product
    >>> plan.bom == bom
    True
    >>> plan.quantity = 1
    >>> plan.save()
    >>> plan.click('compute')
    >>> plan.reload()
    >>> len(plan.products) == 2
    True
    >>> c1, = plan.products.find([
    ...     ('product', '=', component1.id),
    ...     ], limit=1)
    >>> c1.quantity == 5.0
    True
    >>> c2, = plan.products.find([
    ...     ('product', '=', component2.id),
    ...     ], limit=1)
    >>> c2.quantity == 150.0
    True
    >>> cA = plan.products.find([
    ...     ('product', '=', componentA.id),
    ...     ], limit=1)
    >>> len(cA) == 0
    True
    >>> cB = plan.products.find([
    ...     ('product', '=', componentB.id),
    ...     ], limit=1)
    >>> len(cB) == 0
    True
    >>> cost, = plan.costs
    >>> cost.rec_name == 'Raw materials'
    True
    >>> plan.cost_price == Decimal('17.5')
    True
    >>> cost.cost == Decimal('17.5')
    True

Create a manual cost and test total cost is updated::

    >>> CostType = Model.get('product.cost.plan.cost.type')
    >>> Cost = Model.get('product.cost.plan.cost')
    >>> costtype = CostType(name='Manual')
    >>> costtype.save()
    >>> cost = Cost()
    >>> cost.type = costtype
    >>> cost.cost = Decimal('25.0')
    >>> plan.costs.append(cost)
    >>> plan.save()
    >>> plan.reload()
    >>> plan.cost_price
    Decimal('42.5000')

Duplicate cost plan and change plan's product::

    >>> plan2_id, = CostPlan.copy([plan.id], config.context)
    >>> plan2 = CostPlan(plan2_id)
    >>> plan2.bom == None
    True
    >>> plan2.product = product2
    >>> plan2.save()
    >>> len(plan2.products)
    2

Update product's cost price::

    >>> plan2.cost_price
    Decimal('42.5000')
    >>> product2.template.cost_price
    Decimal('0')
    >>> plan2.click('update_product_cost_price')
    >>> product2.reload()
    >>> product2.template.cost_price
    Decimal('42.5000')

Create BoM from cost plan::

    >>> create_bom = Wizard('product.cost.plan.create_bom', [plan2])
    >>> create_bom.execute('bom')
    >>> plan2.reload()
    >>> plan2.bom != None
    True
    >>> plan2.bom != bom
    True
    >>> product2.reload()
    >>> len(product2.boms)
    1
    >>> product2.boms[0].bom == plan2.bom
    True
    >>> len(plan2.bom.inputs)
    2
    >>> sorted([(i.quantity, i.product.rec_name, i.uom.symbol)
    ...         for i in plan2.bom.inputs])
    [(5.0, u'component 1', u'u'), (150.0, u'component 2', u'cm')]
    >>> len(plan2.bom.outputs)
    1
    >>> plan2.bom.outputs[0].product == product2
    True
    >>> plan2.bom.outputs[0].uom == plan2.uom
    True
    >>> plan2.bom.outputs[0].quantity == plan2.quantity
    True

Create plan from scratch::

    >>> plan3 = CostPlan()
    >>> plan3.product = product3
    >>> plan3.uom.symbol
    u'u'
    >>> plan3.bom
    >>> plan3.quantity = 2
    >>> plan3.click('compute')
    >>> plan3.reload()
    >>> len(plan3.products)
    0
    >>> len(plan3.costs)
    1
    >>> product_line = plan3.products_tree.new()
    >>> product_line.product = component1
    >>> product_line.cost_price
    Decimal('2.0000')
    >>> product_line.quantity = 14
    >>> product_line.uom.symbol
    u'u'
    >>> product_line2 = product_line.children.new()
    >>> product_line2.plan = plan3
    >>> product_line2.product = component2
    >>> product_line2.cost_price
    Decimal('5.0000')
    >>> product_line2.quantity = 4
    >>> product_line2.uom.symbol
    u'm'
    >>> product_line2.uom = centimeter
    >>> product_line2.cost_price
    Decimal('0.0500')
    >>> product_line2.cost_price = Decimal('0.0450')
    >>> product_line2.uom.symbol
    u'cm'
    >>> plan3.save()
    >>> product_line, = plan3.products_tree
    >>> product_line.unit_cost
    Decimal('14.0000')
    >>> product_line.total_cost
    Decimal('28.0000')
    >>> product_line2, = product_line.children
    >>> product_line2.unit_cost
    Decimal('1.2600')
    >>> product_line2.total_cost
    Decimal('2.5200')
    >>> cost, = plan3.costs
    >>> cost.rec_name == 'Raw materials'
    True
    >>> cost.cost
    Decimal('15.2600')
    >>> plan3.cost_price
    Decimal('15.2600')

Create BoM from Cost Plan::

    >>> create_bom = Wizard('product.cost.plan.create_bom', [plan3])
    >>> create_bom.execute('bom')
    >>> plan3.reload()
    >>> product3.reload()
    >>> plan3.bom == product3.boms[0].bom
    True
    >>> len(plan3.bom.inputs)
    2
    >>> sorted([(i.quantity, i.product.rec_name, i.uom.symbol)
    ...         for i in plan3.bom.inputs])
    [(14.0, u'component 1', u'u'), (56.0, u'component 2', u'cm')]
    >>> len(plan3.bom.outputs)
    1
    >>> plan3.bom.outputs[0].product == product3
    True
    >>> plan3.bom.outputs[0].quantity
    2.0
