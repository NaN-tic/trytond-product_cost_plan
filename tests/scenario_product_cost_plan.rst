===================
Production Scenario
===================

=============
General Setup
=============

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import config, Model, Wizard
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install production Module::

    >>> Module = Model.get('ir.module.module')
    >>> modules = Module.find([('name', '=', 'product_cost_plan')])
    >>> Module.install([x.id for x in modules], config.context)
    >>> Wizard('ir.module.module.install_upgrade').execute('upgrade')

Create company::

    >>> Currency = Model.get('currency.currency')
    >>> CurrencyRate = Model.get('currency.currency.rate')
    >>> Company = Model.get('company.company')
    >>> Party = Model.get('party.party')
    >>> company_config = Wizard('company.company.config')
    >>> company_config.execute('company')
    >>> company = company_config.form
    >>> party = Party(name='Dunder Mifflin')
    >>> party.save()
    >>> company.party = party
    >>> currencies = Currency.find([('code', '=', 'USD')])
    >>> if not currencies:
    ...     currency = Currency(name='Euro', symbol=u'$', code='USD',
    ...         rounding=Decimal('0.01'), mon_grouping='[3, 3, 0]',
    ...         mon_decimal_point=',')
    ...     currency.save()
    ...     CurrencyRate(date=today + relativedelta(month=1, day=1),
    ...         rate=Decimal('1.0'), currency=currency).save()
    ... else:
    ...     currency, = currencies
    >>> company.currency = currency
    >>> company_config.execute('add')
    >>> company, = Company.find()

Reload the context::

    >>> User = Model.get('res.user')
    >>> config._context = User.get_preferences(True, config.context)

Configuration production location::

    >>> Location = Model.get('stock.location')
    >>> warehouse, = Location.find([('code', '=', 'WH')])
    >>> production_location, = Location.find([('code', '=', 'PROD')])
    >>> warehouse.production_location = production_location
    >>> warehouse.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal(30)
    >>> template.cost_price = Decimal(20)
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Create Components::

    >>> meter, = ProductUom.find([('name', '=', 'Meter')])
    >>> centimeter, = ProductUom.find([('name', '=', 'centimeter')])
    >>> componentA = Product()
    >>> templateA = ProductTemplate()
    >>> templateA.name = 'component A'
    >>> templateA.default_uom = meter
    >>> templateA.type = 'goods'
    >>> templateA.list_price = Decimal(2)
    >>> templateA.cost_price = Decimal(1)
    >>> templateA.save()
    >>> componentA.template = templateA
    >>> componentA.save()

    >>> componentB = Product()
    >>> templateB = ProductTemplate()
    >>> templateB.name = 'component B'
    >>> templateB.default_uom = meter
    >>> templateB.type = 'goods'
    >>> templateB.list_price = Decimal(2)
    >>> templateB.cost_price = Decimal(1)
    >>> templateB.save()
    >>> componentB.template = templateB
    >>> componentB.save()

    >>> component1 = Product()
    >>> template1 = ProductTemplate()
    >>> template1.name = 'component 1'
    >>> template1.default_uom = unit
    >>> template1.type = 'goods'
    >>> template1.list_price = Decimal(5)
    >>> template1.cost_price = Decimal(2)
    >>> template1.save()
    >>> component1.template = template1
    >>> component1.save()

    >>> component2 = Product()
    >>> template2 = ProductTemplate()
    >>> template2.name = 'component 2'
    >>> template2.default_uom = meter
    >>> template2.type = 'goods'
    >>> template2.list_price = Decimal(7)
    >>> template2.cost_price = Decimal(5)
    >>> template2.save()
    >>> component2.template = template2
    >>> component2.save()

Create Bill of Material::

    >>> BOM = Model.get('production.bom')
    >>> BOMInput = Model.get('production.bom.input')
    >>> BOMOutput = Model.get('production.bom.output')
    >>> component_bom = BOM(name='component1')
    >>> input1 = BOMInput()
    >>> component_bom.inputs.append(input1)
    >>> input1.product = componentA
    >>> input1.quantity = 1
    >>> input2 = BOMInput()
    >>> component_bom.inputs.append(input2)
    >>> input2.product = componentB
    >>> input2.quantity = 1
    >>> output = BOMOutput()
    >>> component_bom.outputs.append(output)
    >>> output.product = component1
    >>> output.quantity = 1
    >>> component_bom.save()

    >>> ProductBom = Model.get('product.product-production.bom')
    >>> component1.boms.append(ProductBom(bom=component_bom))
    >>> component1.save()

    >>> bom = BOM(name='product')
    >>> input1 = BOMInput()
    >>> bom.inputs.append(input1)
    >>> input1.product = component1
    >>> input1.quantity = 5
    >>> input2 = BOMInput()
    >>> bom.inputs.append(input2)
    >>> input2.product = component2
    >>> input2.quantity = 150
    >>> input2.uom = centimeter
    >>> output = BOMOutput()
    >>> bom.outputs.append(output)
    >>> output.product = product
    >>> output.quantity = 1
    >>> bom.save()

    >>> ProductBom = Model.get('product.product-production.bom')
    >>> product.boms.append(ProductBom(bom=bom))
    >>> product.save()

Create a cost plan for product (without child boms)::

    >>> CostPlan = Model.get('product.cost.plan')
    >>> plan = CostPlan()
    >>> plan.product = product
    >>> len(plan.boms) == 1
    True
    >>> plan.boms[0].bom == None
    True
    >>> plan.quantity = 10
    >>> plan.save()
    >>> plan.state
    u'draft'
    >>> CostPlan.compute([plan.id], config.context)
    >>> plan.reload()
    >>> plan.state
    u'computed'
    >>> len(plan.products) == 2
    True
    >>> c1, = plan.products.find([
    ...     ('product', '=', component1.id),
    ...     ], limit=1)
    >>> c1.quantity == 50.0
    True
    >>> c2, = plan.products.find([
    ...     ('product', '=', component2.id),
    ...     ], limit=1)
    >>> c2.quantity == 1500.0
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
    >>> plan.total_cost == Decimal('175.0')
    True

Create a cost plan for product (with child boms)::

    >>> CostPlan = Model.get('product.cost.plan')
    >>> plan = CostPlan()
    >>> plan.product = product
    >>> len(plan.boms) == 1
    True
    >>> plan.quantity = 10
    >>> plan.save()
    >>> plan.state
    u'draft'
    >>> for product_bom in plan.boms:
    ...     product_bom.bom = product_bom.product.boms[0]
    ...     product_bom.save()
    >>> plan.reload()
    >>> CostPlan.compute([plan.id], config.context)
    >>> plan.reload()
    >>> plan.state
    u'computed'
    >>> len(plan.products) == 3
    True
    >>> cA, = plan.products.find([
    ...     ('product', '=', componentA.id),
    ...     ], limit=1)
    >>> cA.quantity == 50.0
    True
    >>> cB, = plan.products.find([
    ...     ('product', '=', componentB.id),
    ...     ], limit=1)
    >>> cB.quantity == 50.0
    True
    >>> c2, = plan.products.find([
    ...     ('product', '=', component2.id),
    ...     ], limit=1)
    >>> c2.quantity == 1500.0
    True
    >>> plan.total_cost == Decimal('175.0')
    True

