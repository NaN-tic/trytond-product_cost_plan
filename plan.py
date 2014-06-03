from decimal import Decimal
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval, Bool, If
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateAction, Button
from trytond.config import CONFIG
DIGITS = int(CONFIG.get('unit_price_digits', 4))

__all__ = ['PlanCostType', 'Plan', 'PlanBOM', 'PlanProductLine', 'PlanCost',
    'CreateBomStart', 'CreateBom']


class PlanCostType(ModelSQL, ModelView):
    'Plan Cost Type'
    __name__ = 'product.cost.plan.cost.type'
    name = fields.Char('Name', required=True, translate=True)


class Plan(ModelSQL, ModelView):
    'Product Cost Plan'
    __name__ = 'product.cost.plan'

    number = fields.Char('Number', select=True, readonly=True)
    name = fields.Char('Name', select=True)
    active = fields.Boolean('Active')
    product = fields.Many2One('product.product', 'Product')
    quantity = fields.Float('Quantity', required=True)
    uom = fields.Many2One('product.uom', 'UOM', required=True, domain=[
            If(Bool(Eval('product_uom_category')),
                ('category', '=', Eval('product_uom_category')),
                (),
            )],
        states={
            'readonly': Bool(Eval('product')),
            }, depends=['product_uom_category', 'product'])
    product_uom_category = fields.Function(
        fields.Many2One('product.uom.category', 'Product Uom Category'),
        'on_change_with_product_uom_category')
    bom = fields.Many2One('production.bom', 'BOM',
        depends=['product'], domain=[
            ('output_products', '=', Eval('product', 0)),
            ])
    boms = fields.One2Many('product.cost.plan.bom_line', 'plan', 'BOMs')
    products = fields.One2Many('product.cost.plan.product_line', 'plan',
        'Products')
    products_tree = fields.Function(
        fields.One2Many('product.cost.plan.product_line', 'plan', 'Products'),
        'get_products_tree', setter='set_products_tree')
    product_cost = fields.Function(fields.Numeric('Product Cost',
            digits=(16, DIGITS)),
        'on_change_with_product_cost')
    costs = fields.One2Many('product.cost.plan.cost', 'plan', 'Costs')
    cost_price = fields.Function(fields.Numeric('Unit Cost Price',
            digits=(16, DIGITS)),
        'on_change_with_cost_price')
    notes = fields.Text('Notes')

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        cls._buttons.update({
                'compute': {
                    'icon': 'tryton-spreadsheet',
                    },
                })
        cls._error_messages.update({
                'bom_already_exists': ('A bom already exists for cost plan '
                    '"%s".'),
                'cannot_mix_input_uoms': ('Product "%(product)s" in Cost Plan '
                    '"%(plan)s" has different units of measure.'),
                'product_already_has_bom': ('Product "%s" already has a BOM '
                    'assigned.'),
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

    def get_products_tree(self, name):
        return [x.id for x in self.products if not x.parent]

    @classmethod
    def set_products_tree(cls, lines, name, value):
        cls.write(lines, {
                'products': value,
                })

    @fields.depends('product', 'bom', 'boms')
    def on_change_product(self):
        res = {'bom': None}
        bom = self.on_change_with_bom()
        self.bom = bom
        res['boms'] = self.on_change_with_boms()
        if self.product:
            res['uom'] = self.product.default_uom.id
        return res

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

    def update_cost_type(self, module, id, value):
        """
        Updates the cost line for type_ with value of field
        """
        pool = Pool()
        CostType = pool.get('product.cost.plan.cost.type')
        ModelData = pool.get('ir.model.data')

        type_ = CostType(ModelData.get_id(module, id))
        res = {}
        to_update = []
        for cost in self.costs:
            if cost.type == type_ and cost.system:
                to_update.append(cost.update_cost_values(value))
                cost.cost = value
        if to_update:
            res['cost_price'] = self.on_change_with_cost_price()
            res['costs'] = {'update': to_update}
        return res

    @fields.depends('products', 'costs', 'product_cost')
    def on_change_products(self):
        self.product_cost = self.on_change_with_product_cost()
        return self.update_cost_type('product_cost_plan', 'raw_materials',
            self.product_cost)

    @fields.depends('products_tree', 'costs', 'quantity')
    def on_change_products_tree(self):
        self.product_cost = self.on_change_with_product_cost()
        res = self.update_cost_type('product_cost_plan', 'raw_materials',
            self.product_cost)
        res['product_cost'] = self.product_cost
        return res

    @fields.depends('products_tree', 'quantity')
    def on_change_with_product_cost(self, name=None):
        if not self.quantity:
            return Decimal('0.0')
        cost = sum(p.total for p in self.products_tree if p.total)
        cost /= Decimal(str(self.quantity))
        digits = self.__class__.product_cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    @fields.depends('costs', 'quantity')
    def on_change_with_cost_price(self, name=None):
        return sum(c.cost for c in self.costs if c.cost)

    @fields.depends('product')
    def on_change_with_product_uom_category(self, name=None):
        if self.product:
            return self.product.default_uom_category.id

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
    def remove_product_lines(cls, plans):
        pool = Pool()
        ProductLine = pool.get('product.cost.plan.product_line')
        CostLine = pool.get('product.cost.plan.cost')

        types = [x[0]for x in cls.get_cost_types()]
        to_delete = []
        costs_to_delete = []
        for plan in plans:
            to_delete.extend(plan.products)
            for line in plan.costs:
                if line.type in types:
                    costs_to_delete.append(line)

        if to_delete:
            ProductLine.delete(to_delete)
        if costs_to_delete:
            with Transaction().set_context(reset_costs=True):
                CostLine.delete(costs_to_delete)

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
                        1, plan.product.default_uom))
        if to_create:
            ProductLine.create(to_create)

        to_create = []
        for plan in plans:
            to_create.extend(plan.get_costs())
        if to_create:
            CostLine.create(to_create)

    def get_costs(self):
        "Returns the cost lines to be created on compute"
        ret = []
        for cost_type, field_name in self.get_cost_types():
            ret.append(self.get_cost_line(cost_type, field_name))
        return ret

    def get_cost_line(self, cost_type, field_name):
        cost = getattr(self, field_name, 0.0)
        return {
            'type': cost_type.id,
            'cost': Decimal(str(cost)),
            'plan': self.id,
            'system': True,
            }

    @classmethod
    def get_cost_types(cls):
        """
        Returns a list of values with the cost types and the field to get
        their cost.
        """
        pool = Pool()
        CostType = pool.get('product.cost.plan.cost.type')
        ModelData = pool.get('ir.model.data')
        ret = []
        type_ = CostType(ModelData.get_id('product_cost_plan',
                'raw_materials'))
        ret.append((type_, 'product_cost'))
        return ret

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
        Uom = pool.get('product.uom')
        Input = pool.get('production.bom.input')
        ProductLine = pool.get('product.cost.plan.product_line')
        quantity = Input.compute_quantity(input_, factor)
        cost_factor = Decimal(Uom.compute_qty(input_.product.default_uom, 1,
            input_.uom))
        digits = ProductLine.product_cost_price.digits[1]
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

    @classmethod
    def delete(cls, plans):
        CostLine = Pool().get('product.cost.plan.cost')
        to_delete = []
        for plan in plans:
            to_delete += plan.costs
        with Transaction().set_context(reset_costs=True):
            CostLine.delete(to_delete)
        super(Plan, cls).delete(plans)

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
            output.uom = self.product.default_uom
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
        return input_


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
    product = fields.Many2One('product.product', 'Product',
        domain=[
            ('type', '!=', 'service'),
        ])
    quantity = fields.Float('Quantity', required=True,
        digits=(16, Eval('uom_digits', 2)), depends=['uom_digits'])
    uom_category = fields.Function(fields.Many2One(
        'product.uom.category', 'Uom Category'), 'on_change_with_uom_category')
    uom = fields.Many2One('product.uom', 'Uom', required=True,
        domain=[
            If(Bool(Eval('product', 0)),
            ('category', '=', Eval('uom_category')),
            ('id', '!=', 0),
            )
            ], depends=['uom_category', 'product'])
    uom_digits = fields.Function(fields.Integer('UOM Digits'),
        'on_change_with_uom_digits')
    product_cost_price = fields.Numeric('Product Cost Price',
        digits=(16, DIGITS),
        states={
            'readonly': True,
            }, depends=['product'])
    cost_price = fields.Numeric('Cost Price', required=True,
        digits=(16, DIGITS))
    total = fields.Function(fields.Numeric('Total Cost',
            digits=(16, DIGITS)), 'on_change_with_total')
    total_unit = fields.Function(fields.Numeric('Total Unit Cost',
            digits=(16, DIGITS)), 'on_change_with_total_unit')

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

    @fields.depends('product')
    def on_change_with_uom_category(self, name=None):
        if self.product:
            return self.product.default_uom.category.id

    @fields.depends('product', 'uom')
    def on_change_with_product_cost_price(self):
        Uom = Pool().get('product.uom')
        if not self.product or not self.uom:
            return
        cost = Decimal(Uom.compute_qty(self.product.default_uom,
            float(self.product.cost_price), self.uom, round=False))
        digits = self.__class__.product_cost_price.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    @fields.depends('quantity', 'cost_price', 'uom', 'product', 'children')
    def on_change_with_total(self, name=None):
        quantity = self.quantity
        if not quantity:
            return Decimal('0.0')
        total = Decimal(str(quantity)) * (self.cost_price or Decimal('0.0'))
        for child in self.children:
            total += Decimal(str(quantity)) * (child.total or Decimal('0.0'))
        digits = self.__class__.total.digits[1]
        return total.quantize(Decimal(str(10 ** -digits)))

    @fields.depends('quantity', 'cost_price', 'uom', 'product', 'children',
        '_parent_plan.quantity')
    def on_change_with_total_unit(self, name=None):
        total = self.on_change_with_total(None)
        if total and self.plan and self.plan.quantity:
            total /= Decimal(str(self.plan.quantity))
        else:
            total = Decimal('0.0')
        digits = self.__class__.total_unit.digits[1]
        return total.quantize(Decimal(str(10 ** -digits)))

    @fields.depends('uom')
    def on_change_with_uom_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2


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
    type = fields.Many2One('product.cost.plan.cost.type', 'Type',
        required=True, states=STATES, depends=DEPENDS)
    cost = fields.Numeric('Cost', required=True, states=STATES,
        depends=DEPENDS, digits=(16, DIGITS))
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
    def default_system():
        return False

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == None, table.sequence]

    def get_rec_name(self, name):
        return self.type.rec_name

    @classmethod
    def search_rec_name(cls, name, clause):
        return [('type.name',) + tuple(clause[1:])]

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

    def update_cost_values(self, value):
        return {
            'cost': value,
            'id': self.id,
            }


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
