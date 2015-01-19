# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal

from trytond.config import config
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval, Bool, If
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateAction, Button

DIGITS = int(config.get('digits', 'unit_price_digits', 4))

__all__ = ['PlanCostType', 'Plan', 'PlanBOM', 'PlanProductLine', 'PlanCost',
    'CreateBomStart', 'CreateBom']


class PlanCostType(ModelSQL, ModelView):
    'Plan Cost Type'
    __name__ = 'product.cost.plan.cost.type'
    name = fields.Char('Name', required=True, translate=True)
    system = fields.Boolean('System Managed', readonly=True)
    plan_field_name = fields.Char('Plan Field Name', readonly=True)


class Plan(ModelSQL, ModelView):
    'Product Cost Plan'
    __name__ = 'product.cost.plan'

    number = fields.Char('Number', select=True, readonly=True)
    name = fields.Char('Name', select=True)
    active = fields.Boolean('Active')
    product = fields.Many2One('product.product', 'Product')
    product_uom_category = fields.Function(
        fields.Many2One('product.uom.category', 'Product UoM Category'),
        'on_change_with_product_uom_category')
    quantity = fields.Float('Quantity', digits=(16, Eval('uom_digits', 2)),
        required=True, depends=['uom_digits'])
    uom = fields.Many2One('product.uom', 'UoM', required=True, domain=[
            If(Bool(Eval('product')),
                ('category', '=', Eval('product_uom_category')),
                ('id', '!=', -1),
            )],
        states={
            'readonly': Bool(Eval('product')),
            }, depends=['product', 'product_uom_category'])
    uom_digits = fields.Function(fields.Integer('UoM Digits'),
        'on_change_with_uom_digits')
    bom = fields.Many2One('production.bom', 'BOM',
        depends=['product'], domain=[
            ('output_products', '=', Eval('product', 0)),
            ])
    boms = fields.One2Many('product.cost.plan.bom_line', 'plan', 'BOMs')
    products = fields.One2Many('product.cost.plan.product_line', 'plan',
        'Products')
    products_tree = fields.Function(
        fields.One2Many('product.cost.plan.product_line', 'plan', 'Products',
            domain=[
                ('parent', '=', None),
                ],
            states={
                'readonly': ~Bool(Eval('costs', [0])),
                },
            depends=['costs']),
        'get_products_tree', setter='set_products_tree')
    products_cost = fields.Function(fields.Numeric('Products Cost',
            digits=(16, DIGITS)),
        'get_products_cost')
    costs = fields.One2Many('product.cost.plan.cost', 'plan', 'Costs')
    cost_price = fields.Function(fields.Numeric('Unit Cost Price',
            digits=(16, DIGITS)),
        'get_cost_price')
    notes = fields.Text('Notes')

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        cls._buttons.update({
                'compute': {
                    'icon': 'tryton-spreadsheet',
                    },
                'update_product_prices': {
                    'icon': 'tryton-refresh',
                    },
                })
        cls._error_messages.update({
                'product_lines_will_be_removed': (
                    'It will remove the existing Product Lines in this plan.'),
                'bom_already_exists': (
                    'A bom already exists for cost plan "%s".'),
                'cannot_mix_input_uoms': ('Product "%(product)s" in Cost Plan '
                    '"%(plan)s" has different units of measure.'),
                'product_already_has_bom': (
                    'Product "%s" already has a BOM assigned.'),
                })


    @staticmethod
    def default_active():
        return True

    @staticmethod
    def default_state():
        return 'draft'

    def get_rec_name(self, name):
        res = '[%s]' % self.number
        if self.name:
            res += ' ' + self.name
        return res

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('number',) + tuple(clause[1:]),
            ('name',) + tuple(clause[1:]),
            ]

    @fields.depends('product', 'bom', 'boms')
    def on_change_product(self):
        res = {'bom': None}
        bom = self.on_change_with_bom()
        self.bom = bom
        res['boms'] = self.on_change_with_boms()
        if self.product:
            res['uom'] = self.product.default_uom.id
        return res

    @fields.depends('uom')
    def on_change_with_uom_digits(self, name=None):
        return self.uom.digits if self.uom else 2

    @fields.depends('product', 'uom')
    def on_change_with_product_uom_category(self, name=None):
        if self.product:
            return self.product.default_uom_category.id
        if self.uom:
            return self.uom.category.id

    @fields.depends('product')
    def on_change_with_bom(self):
        BOM = Pool().get('production.bom')
        if not self.product:
            return
        boms = BOM.search([('output_products', '=', self.product.id)])
        if boms:
            return boms[0].id

    @fields.depends('bom', 'boms', 'product')
    def on_change_with_boms(self):
        boms = {
            'remove': [x.id for x in self.boms],
            'add': [],
            }
        if not self.bom:
            return boms

        def find_boms(inputs):
            res = []
            for input_ in inputs:
                if input_.product.boms:
                    product_bom = input_.product.boms[0].bom
                    res.append((input_.product.id, product_bom.id))
                    res += find_boms(product_bom.inputs)
            return res

        products = set(find_boms(self.bom.inputs))
        for index, (product_id, bom_id) in enumerate(products):
            boms['add'].append((index, {
                        'product': product_id,
                        'bom': None,
                        }))
        return boms

    def get_products_tree(self, name):
        return [x.id for x in self.products if not x.parent]

    @classmethod
    def set_products_tree(cls, lines, name, value):
        cls.write(lines, {
                'products': value,
                })

    def get_products_cost(self, name):
        if not self.quantity:
            return Decimal('0.0')
        cost = sum(p.get_total_cost(None, round=False) for p in self.products)
        cost /= Decimal(str(self.quantity))
        digits = self.__class__.products_cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    def get_cost_price(self, name):
        return sum(c.cost for c in self.costs if c.cost)

    @classmethod
    def remove_product_lines(cls, plans):
        pool = Pool()
        ProductLine = pool.get('product.cost.plan.product_line')
        CostLine = pool.get('product.cost.plan.cost')

        product_lines = ProductLine.search([
                ('plan', 'in', [p.id for p in plans]),
                ])
        if product_lines:
            cls.raise_user_warning('remove_product_lines',
                'product_lines_will_be_removed')
            ProductLine.delete(product_lines)

        with Transaction().set_context(reset_costs=True):
            CostLine.delete(CostLine.search([
                        ('plan', 'in', [p.id for p in plans]),
                        ('system', '=', True),
                        ]))

    @classmethod
    @ModelView.button
    def compute(cls, plans):
        pool = Pool()
        ProductLine = pool.get('product.cost.plan.product_line')
        CostLine = pool.get('product.cost.plan.cost')

        cls.remove_product_lines(plans)
        to_create = []
        for plan in plans:
            if plan.product and plan.bom:
                to_create.extend(plan.explode_bom(plan.product, plan.bom,
                        plan.quantity, plan.uom))
        if to_create:
            ProductLine.create(to_create)

        to_create = []
        for plan in plans:
            to_create.extend(plan.get_costs())
        if to_create:
            CostLine.create(to_create)

    def explode_bom(self, product, bom, quantity, uom):
        "Returns products for the especified products"
        pool = Pool()
        Input = pool.get('production.bom.input')
        res = []

        plan_boms = {}
        for plan_bom in self.boms:
            if plan_bom.bom:
                plan_boms[plan_bom.product.id] = plan_bom.bom

        factor = bom.compute_factor(product, quantity, uom)

        for input_ in bom.inputs:
            product = input_.product
            if product.id in plan_boms:
                quantity = Input.compute_quantity(input_, factor)
                res.extend(self.explode_bom(product, plan_boms[product.id],
                        quantity, input_.uom))
            else:
                line = self.get_product_line(input_, factor)
                if line:
                    line['plan'] = self.id
                    res.append(line)
        return res

    def get_product_line(self, input_, factor):
        """
        Returns a dict with values of the new line to create
        params:
            *input_*: Production.bom.input record for the product
            *factor*: The factor to calculate the quantity
        """
        pool = Pool()
        UoM = pool.get('product.uom')
        Input = pool.get('production.bom.input')
        ProductLine = pool.get('product.cost.plan.product_line')
        quantity = Input.compute_quantity(input_, factor)
        cost_factor = Decimal(UoM.compute_qty(input_.product.default_uom, 1,
            input_.uom))
        digits = ProductLine.product_cost_price.digits[1]
        if cost_factor == Decimal('0.0'):
            product_cost_price = Decimal('0.0')
            cost_price = Decimal('0.0')
        else:
            product_cost_price = (input_.product.cost_price /
                cost_factor).quantize(Decimal(str(10 ** -digits)))
            digits = ProductLine.cost_price.digits[1]
            cost_price = (input_.product.cost_price /
                cost_factor).quantize(Decimal(str(10 ** -digits)))

        return {
            'name': input_.product.rec_name,
            'product': input_.product.id,
            'quantity': quantity,
            'uom': input_.uom.id,
            'product_cost_price': product_cost_price,
            'cost_price': cost_price,
            }

    def get_costs(self):
        "Returns the cost lines to be created on compute"
        pool = Pool()
        CostType = pool.get('product.cost.plan.cost.type')

        ret = []
        system_cost_types = CostType.search([
                ('system', '=', True),
                ])
        for cost_type in system_cost_types:
            ret.append(self._get_cost_line(cost_type))
        return ret

    def _get_cost_line(self, cost_type):
        return {
            'plan': self.id,
            'type': cost_type.id,
            'system': True,
            }

    @classmethod
    @ModelView.button
    def update_product_prices(cls, plans):
        for plan in plans:
            if not plan.product:
                continue
            plan._update_product_prices()
            plan.product.save()
            plan.product.template.save()

    def _update_product_prices(self):
        pool = Pool()
        Uom = pool.get('product.uom')

        assert self.product
        cost_price = Uom.compute_price(self.uom, self.cost_price,
            self.product.default_uom)
        if hasattr(self.product.__class__, 'cost_price'):
            digits = self.product.__class__.cost_price.digits[1]
            cost_price = cost_price.quantize(Decimal(str(10 ** -digits)))
            self.product.cost_price = cost_price
        else:
            digits = self.product.template.__class__.cost_price.digits[1]
            cost_price = cost_price.quantize(Decimal(str(10 ** -digits)))
            self.product.template.cost_price = cost_price

    def create_bom(self, name):
        pool = Pool()
        BOM = pool.get('production.bom')
        ProductBOM = pool.get('product.product-production.bom')
        if self.bom:
            self.raise_user_error('bom_already_exists', self.rec_name)
        bom = BOM()
        bom.name = name
        bom.inputs = self._get_bom_inputs()
        bom.outputs = self._get_bom_outputs()
        bom.save()
        self.bom = bom
        self.save()

        ProductBOM()
        if self.product.boms:
            product_bom = self.product.boms[0]
            if product_bom.bom:
                self.raise_user_error('product_already_has_bom',
                    self.product.rec_name)
        else:
            product_bom = ProductBOM()
        product_bom.product = self.product
        product_bom.bom = bom
        product_bom.save()
        return bom

    def _get_bom_outputs(self):
        BOMOutput = Pool().get('production.bom.output')
        outputs = []
        if self.product:
            output = BOMOutput()
            output.product = self.product
            output.uom = self.uom
            output.quantity = self.quantity
            outputs.append(output)
        return outputs

    def _get_bom_inputs(self):
        inputs = {}
        for line in self.products:
            if not line.product:
                continue
            input_ = self._get_input_line(line)
            if input_.product.id not in inputs:
                inputs[input_.product.id] = input_
                continue
            existing = inputs[input_.product.id]
            if existing.uom != input_.uom:
                self.raise_user_error('cannot_mix_input_uoms', {
                        'plan': self.rec_name,
                        'product': existing.product.rec_name,
                        })
            existing.quantity += input_.quantity
        return inputs.values()

    def _get_input_line(self, line):
        'Return the BOM Input line for a product line'
        BOMInput = Pool().get('production.bom.input')
        input_ = BOMInput()
        input_.product = line.product
        input_.uom = line.uom
        input_.quantity = line.quantity
        parent_line = line.parent
        while parent_line:
            input_.quantity *= parent_line.quantity
            parent_line = parent_line.parent
        return input_

    @classmethod
    def create(cls, vlist):
        Sequence = Pool().get('ir.sequence')
        Config = Pool().get('production.configuration')

        vlist = [x.copy() for x in vlist]
        config = Config(1)
        for values in vlist:
            values['number'] = Sequence.get_id(
                config.product_cost_plan_sequence.id)
        return super(Plan, cls).create(vlist)

    @classmethod
    def copy(cls, plans, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['products'] = None
        default['products_tree'] = None

        new_plans = []
        for plan in plans:
            new_plans.append(plan._copy_plan(default))
        return new_plans

    def _copy_plan(self, default):
        ProductLine = Pool().get('product.cost.plan.product_line')

        new_plan, = super(Plan, self).copy([self], default=default)
        ProductLine.copy(self.products_tree, default={
                'plan': new_plan.id,
                'children': None,
                })
        return new_plan

    @classmethod
    def delete(cls, plans):
        CostLine = Pool().get('product.cost.plan.cost')
        to_delete = []
        for plan in plans:
            to_delete += plan.costs
        with Transaction().set_context(reset_costs=True):
            CostLine.delete(to_delete)
        super(Plan, cls).delete(plans)


class PlanBOM(ModelSQL, ModelView):
    'Product Cost Plan BOM'
    __name__ = 'product.cost.plan.bom_line'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    product = fields.Many2One('product.product', 'Product', required=True)
    bom = fields.Many2One('production.bom', 'BOM', domain=[
            ('output_products', '=', Eval('product', 0)),
            ], depends=['product'])


class PlanProductLine(ModelSQL, ModelView):
    'Product Cost Plan Product Line'
    __name__ = 'product.cost.plan.product_line'

    name = fields.Char('Name')
    sequence = fields.Integer('Sequence')
    parent = fields.Many2One('product.cost.plan.product_line', 'Parent')
    children = fields.One2Many('product.cost.plan.product_line', 'parent',
        'Children')
    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    product = fields.Many2One('product.product', 'Product', domain=[
            ('type', '!=', 'service'),
            If(Bool(Eval('children')),
                ('default_uom.category', '=', Eval('uom_category')),
                ()),
        ], depends=['children', 'uom_category'])
    quantity = fields.Float('Quantity', required=True,
        digits=(16, Eval('uom_digits', 2)), depends=['uom_digits'])
    uom_category = fields.Function(fields.Many2One('product.uom.category',
            'UoM Category'),
        'on_change_with_uom_category')
    uom = fields.Many2One('product.uom', 'UoM', required=True, domain=[
            If(Bool(Eval('children')) | Bool(Eval('product')),
                ('category', '=', Eval('uom_category')),
                ()),
            ], depends=['children', 'product', 'uom_category'])
    uom_digits = fields.Function(fields.Integer('UoM Digits'),
        'on_change_with_uom_digits')
    product_cost_price = fields.Numeric('Product Cost Price',
        digits=(16, DIGITS),
        states={
            'readonly': True,
            }, depends=['product'])
    cost_price = fields.Numeric('Cost Price', required=True,
        digits=(16, DIGITS))
    unit_cost = fields.Function(fields.Numeric('Unit Cost',
            digits=(16, DIGITS),
            help="The cost of this product for each unit of plan's product."),
        'get_unit_cost')
    total_cost = fields.Function(fields.Numeric('Total Cost',
            digits=(16, DIGITS),
            help="The cost of this product for total plan's quantity."),
        'get_total_cost')

    @classmethod
    def __setup__(cls):
        super(PlanProductLine, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == None, table.sequence]

    @fields.depends('product', 'uom')
    def on_change_product(self):
        res = {}
        if self.product:
            uoms = self.product.default_uom.category.uoms
            if (not self.uom or self.uom not in uoms):
                res['name'] = self.product.rec_name
                res['uom'] = self.product.default_uom.id
                res['uom.rec_name'] = self.product.default_uom.rec_name
                res['product_cost_price'] = self.product.cost_price
                res['cost_price'] = self.product.cost_price
        else:
            res['name'] = None
            res['uom'] = None
            res['uom.rec_name'] = ''
            res['product_cost_price'] = None
        return res

    @fields.depends('children', '_parent_plan.uom' 'product', 'uom')
    def on_change_with_uom_category(self, name=None):
        if self.children:
            # If product line has children, it must be have computable
            # quantities of plan product
            return self.plan.uom.category.id
        if self.product:
            return self.product.default_uom.category.id

    @fields.depends('uom')
    def on_change_with_uom_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    @fields.depends('product', 'uom', 'cost_price')
    def on_change_with_cost_price(self):
        UoM = Pool().get('product.uom')

        if (not self.product or not self.uom
                or (self.cost_price
                    and self.cost_price != self.product.cost_price)):
            cost = self.cost_price
        else:
            cost = UoM.compute_price(self.product.default_uom,
                self.product.cost_price, self.uom)
        if cost:
            digits = self.__class__.cost_price.digits[1]
            return cost.quantize(Decimal(str(10 ** -digits)))
        return cost

    @fields.depends('product', 'uom')
    def on_change_with_product_cost_price(self):
        UoM = Pool().get('product.uom')
        if not self.product:
            return
        if not self.uom:
            cost = self.product.cost_price
        else:
            cost = UoM.compute_price(self.product.default_uom,
                self.product.cost_price, self.uom)
        digits = self.__class__.product_cost_price.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    def get_unit_cost(self, name):
        unit_cost = self.total_cost
        if unit_cost and self.plan and self.plan.quantity:
            unit_cost /= Decimal(str(self.plan.quantity))
        digits = self.__class__.unit_cost.digits[1]
        return unit_cost.quantize(Decimal(str(10 ** -digits)))

    def get_total_cost(self, name, round=True):
        if not self.cost_price:
            return Decimal('0.0')
        # Quantity is the quantity of this line for all plan's quantity
        quantity = self.quantity
        line = self
        while quantity and line.parent:
            quantity *= line.parent.quantity
            line = line.parent
        if not quantity:
            return Decimal('0.0')

        total_cost = Decimal(str(quantity)) * self.cost_price
        if not round:
            return total_cost
        digits = self.__class__.total_cost.digits[1]
        return total_cost.quantize(Decimal(str(10 ** -digits)))

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['children'] = None

        new_lines = []
        for line in lines:
            new_line, = super(PlanProductLine, cls).copy([line],
                default=default)
            new_lines.append(new_line)

            new_default = default.copy()
            new_default['parent'] = new_line.id
            cls.copy(line.children, default=new_default)
        return new_lines


STATES = {
    'readonly': Eval('system', False),
    }
DEPENDS = ['system']


class PlanCost(ModelSQL, ModelView):
    'Plan Cost'
    __name__ = 'product.cost.plan.cost'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    sequence = fields.Integer('Sequence')
    type = fields.Many2One('product.cost.plan.cost.type', 'Type', domain=[
            ('system', '=', Eval('system')),
            ],
        required=True, states=STATES, depends=DEPENDS)
    internal_cost = fields.Numeric('Cost (Internal Use)', digits=(16, DIGITS),
        readonly=True)
    cost = fields.Function(fields.Numeric('Cost', digits=(16, DIGITS),
            required=True, states=STATES, depends=DEPENDS),
        'get_cost', setter='set_cost')
    system = fields.Boolean('System Managed', readonly=True)

    @classmethod
    def __setup__(cls):
        super(PlanCost, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))
        cls._error_messages.update({
                'delete_system_cost': ('You can not delete cost "%(cost)s" '
                    'from plan "%(plan)s" because it\'s managed by system.'),
                })

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == None, table.sequence]

    def get_rec_name(self, name):
        return self.type.rec_name

    @classmethod
    def search_rec_name(cls, name, clause):
        return [('type.name',) + tuple(clause[1:])]

    @staticmethod
    def default_system():
        return False

    def get_cost(self, name):
        if self.system:
            cost = getattr(self.plan, self.type.plan_field_name)
        else:
            cost = self.internal_cost
        digits = self.__class__.cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    @classmethod
    def set_cost(cls, records, name, value):
        records_todo = [r for r in records if not r.system]
        cls.write(records, {
                'internal_cost': value,
                })

    @classmethod
    def delete(cls, costs):
        if not Transaction().context.get('reset_costs', False):
            for cost in costs:
                if cost.system:
                    cls.raise_user_error('delete_system_cost', {
                            'cost': cost.rec_name,
                            'plan': cost.plan.rec_name,
                            })
        super(PlanCost, cls).delete(costs)


class CreateBomStart(ModelView):
    'Create BOM Start'
    __name__ = 'product.cost.plan.create_bom.start'

    name = fields.Char('Name', required=True)


class CreateBom(Wizard):
    'Create BOM'
    __name__ = 'product.cost.plan.create_bom'

    start = StateView('product.cost.plan.create_bom.start',
        'product_cost_plan.create_bom_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Ok', 'bom', 'tryton-ok', True),
            ])
    bom = StateAction('production.act_bom_list')

    def default_start(self, fields):
        CostPlan = Pool().get('product.cost.plan')
        plan = CostPlan(Transaction().context.get('active_id'))
        return {
            'name': plan.product.rec_name,
            }

    def do_bom(self, action):
        CostPlan = Pool().get('product.cost.plan')
        plan = CostPlan(Transaction().context.get('active_id'))
        bom = plan.create_bom(self.start.name)
        data = {
            'res_id': [bom.id]
            }
        action['views'].reverse()
        return action, data
