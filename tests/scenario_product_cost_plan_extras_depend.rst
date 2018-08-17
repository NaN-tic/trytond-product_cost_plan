========================================
Product Cost Plan Extras Depend Scenario
========================================

=============
General Setup
=============

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import config, Model, Wizard
    >>> from trytond.tests.tools import activate_modules
    >>> today = datetime.date.today()
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> today = datetime.date.today()


Install product_cost_plan Module::

    >>> config = activate_modules(['product_cost_plan', 'production_external_party'])

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
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal(30)
    >>> template.producible = True
    >>> template.save()
    >>> product, = template.products
    >>> product.cost_price = Decimal(20)
    >>> product.save()

    >>> template = ProductTemplate()
    >>> template.name = 'product 2'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal(30)
    >>> template.producible = True
    >>> template.save()
    >>> product2, = template.products

    >>> template = ProductTemplate()
    >>> template.name = 'product 3'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal(15)
    >>> template.producible = True
    >>> template.save()
    >>> product3, = template.products

Create Components::

    >>> meter, = ProductUom.find([('name', '=', 'Meter')])
    >>> centimeter, = ProductUom.find([('name', '=', 'centimeter')])
    >>> template1 = ProductTemplate()
    >>> template1.name = 'component 1'
    >>> template1.default_uom = unit
    >>> template1.type = 'goods'
    >>> template1.list_price = Decimal(5)
    >>> template1.may_belong_to_party = True
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

Create Bill of Material with party stock for component 1::

    >>> BOM = Model.get('production.bom')
    >>> bom = BOM(name='product')
    >>> input1 =  bom.inputs.new()
    >>> input1.product = component1
    >>> input1.party_stock
    1
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

Create a cost plan from BoM::

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
    >>> len(plan.products)
    2
    >>> sorted([(p.quantity, p.product.rec_name, bool(p.party_stock), p.cost_price)
    ...         for p in plan.products])
    [(5.0, 'component 1', True, Decimal('0.0000')), (150.0, 'component 2', False, Decimal('0.0500'))]
    >>> cost, = plan.costs
    >>> cost.rec_name == 'Raw materials'
    True
    >>> cost.cost
    Decimal('7.5000')
    >>> plan.cost_price
    Decimal('7.5000')

Duplicate cost plan and change plan's product::

    >>> plan2_id, = CostPlan.copy([plan.id], config.context)
    >>> plan2 = CostPlan(plan2_id)
    >>> plan2.bom == None
    True
    >>> plan2.product = product2
    >>> plan2.save()
    >>> len(plan2.products)
    2

Set party stock also for second component::

    >>> for product_line in plan2.products:
    ...     if product_line.product == component2:
    ...         product_line.party_stock = True
    >>> plan2.save()
    >>> plan2.reload()
    >>> sorted([(p.quantity, p.product.rec_name, bool(p.party_stock), p.cost_price)
    ...         for p in plan2.products])
    [(5.0, 'component 1', True, Decimal('0.0000')), (150.0, 'component 2', True, Decimal('0.0'))]
    >>> plan2.cost_price
    0

Create BoM from cost plan::

    >>> create_bom = Wizard('product.cost.plan.create_bom', [plan2])
    >>> create_bom.execute('bom')
    >>> plan2.reload()
    >>> product2.reload()
    >>> product2.boms[0].bom == plan2.bom
    True
    >>> len(plan2.bom.inputs)
    2
    >>> sorted([(i.quantity, i.product.rec_name, bool(i.party_stock), i.uom.symbol)
    ...         for i in plan2.bom.inputs])
    [(5.0, 'component 1', True, 'u'), (150.0, 'component 2', True, 'cm')]
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
    'u'
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
    >>> bool(product_line.party_stock)
    True
    >>> product_line.cost_price
    Decimal('0.0')
    >>> product_line.quantity = 14
    >>> product_line.uom.symbol
    'u'
    >>> product_line2 = product_line.children.new()
    >>> product_line2.plan = plan3
    >>> product_line2.product = component2
    >>> product_line2.cost_price
    Decimal('5.0000')
    >>> product_line2.quantity = 4
    >>> product_line2.uom.symbol
    'm'
    >>> product_line2.uom = centimeter
    >>> product_line2.cost_price
    Decimal('0.0500')
    >>> product_line2.cost_price = Decimal('0.0450')
    >>> product_line2.uom.symbol
    'cm'
    >>> plan3.save()
    >>> product_line, = plan3.products_tree
    >>> product_line2, = product_line.children
    >>> product_line2.unit_cost
    Decimal('1.2600')
    >>> product_line2.total_cost
    Decimal('2.5200')
    >>> cost, = plan3.costs
    >>> cost.rec_name == 'Raw materials'
    True
    >>> cost.cost
    Decimal('1.2600')
    >>> plan3.cost_price
    Decimal('1.2600')

Create BoM from Cost Plan::

    >>> create_bom = Wizard('product.cost.plan.create_bom', [plan3])
    >>> create_bom.execute('bom')
    >>> plan3.reload()
    >>> product3.reload()
    >>> plan3.bom == product3.boms[0].bom
    True
    >>> len(plan3.bom.inputs)
    2
    >>> sorted([(i.quantity, i.product.rec_name, bool(i.party_stock), i.uom.symbol)
    ...         for i in plan3.bom.inputs])
    [(14.0, 'component 1', True, 'u'), (56.0, 'component 2', False, 'cm')]
    >>> len(plan3.bom.outputs)
    1
    >>> plan3.bom.outputs[0].product == product3
    True
    >>> plan3.bom.outputs[0].quantity
    2.0
