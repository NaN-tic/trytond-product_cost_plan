from decimal import Decimal
from trytond.model import Workflow, ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval, Bool, If
from trytond.transaction import Transaction

__all__ = ['PlanCostType', 'Plan', 'PlanBOM', 'PlanProductLine', 'PlanCost']


class PlanCostType(ModelSQL, ModelView):
    'Plan Cost Type'
    __name__ = 'product.cost.plan.cost.type'
    name = fields.Char('Name', required=True, translate=True)


class Plan(Workflow, ModelSQL, ModelView):
    'Product Cost Plan'
    __name__ = 'product.cost.plan'

    number = fields.Char('Number')
    product = fields.Many2One('product.product', 'Product',
        states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'], on_change=['product', 'bom', 'boms'])
    bom = fields.Many2One('production.bom', 'BOM', on_change_with=['product'],
        states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state', 'product'],
        domain=[
            ('output_products', '=', Eval('product', 0)),
            ])
    boms = fields.One2Many('product.cost.plan.bom_line', 'plan', 'BOMs',
        states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'], on_change_with=['bom', 'boms'])
    quantity = fields.Float('Quantity', required=True, states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'])
    products = fields.One2Many('product.cost.plan.product_line', 'plan',
        'Products', states={
            'readonly': Eval('state') == 'draft',
            },
        depends=['state'],
        on_change=['costs', 'products'])
    product_cost = fields.Function(fields.Numeric('Product Cost',
            on_change_with=['products']), 'on_change_with_product_cost')
    costs = fields.One2Many('product.cost.plan.cost', 'plan', 'Costs')
    total_cost = fields.Function(fields.Numeric('Total Cost',
            on_change_with=['costs']),
        'on_change_with_total_cost')
    unit_cost_price = fields.Function(fields.Numeric('Unit Cost Price'),
        'get_unit_cost_price')
    state = fields.Selection([
            ('draft', 'Draft'),
            ('computed', 'Computed'),
            ], 'State', readonly=True)

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        cls._transitions |= set((
                ('draft', 'computed'),
                ('computed', 'draft'),
                ))
        cls._buttons.update({
                'compute': {
                    'invisible': Eval('state') == 'computed',
                    'icon': 'tryton-go-next',
                    },
                'reset': {
                    'invisible': Eval('state') == 'draft',
                    'icon': 'tryton-go-previous',
                    }
                })

    @staticmethod
    def default_state():
        return 'draft'

    def on_change_product(self):
        res = {'bom': None}
        bom = self.on_change_with_bom()
        self.bom = bom
        res['boms'] = self.on_change_with_boms()
        return res

    def on_change_with_bom(self):
        BOM = Pool().get('production.bom')
        if not self.product:
            return
        boms = BOM.search([('output_products', '=', self.product.id)])
        if boms:
            return boms[0].id

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
                    res.append(input_.product.id)
                    for product_bom in input_.product.boms:
                        if product_bom.bom and product_bom.bom.inputs:
                            res.extend(find_boms(product_bom.bom.inputs))
            return res

        products = set(find_boms(self.bom.inputs))
        for product in products:
            boms['add'].append({
                    'product': product,
                    })
        return boms

    def update_cost_type(self, type_, value):
        """
        Updates the cost line for type_ with value of field
        """
        res = {}
        to_update = []
        for cost in self.costs:
            if cost.type == type_ and cost.system:
                to_update.append(cost.update_cost_values(value))
                cost.cost = value
        if to_update:
            res['costs'] = {'update': to_update}
            res['total_cost'] = self.on_change_with_total_cost()
        return res

    def on_change_products(self):
        pool = Pool()
        CostType = pool.get('product.cost.plan.cost.type')
        ModelData = pool.get('ir.model.data')

        type_ = CostType(ModelData.get_id('product_cost_plan',
                'raw_materials'))
        self.product_cost = sum(p.total for p in self.products if p.total)
        return self.update_cost_type(type_, self.product_cost)

    def on_change_with_product_cost(self, name=None):
	cost = sum(p.total for p in self.products if p.total)
        return cost

    def on_change_with_total_cost(self, name=None):
	cost = sum(c.cost for c in self.costs if c.cost)
        return cost

    def get_unit_cost_price(self, name):
        total_cost = self.total_cost
        if self.quantity and total_cost:
            return total_cost / Decimal(str(self.quantity))
        return Decimal('0.0')

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def reset(cls, plans):
        pool = Pool()
        ProductLines = pool.get('product.cost.plan.product_line')
        CostLines = pool.get('product.cost.plan.cost')

        types = [x[0]for x in cls.get_cost_types()]
        to_delete = []
        costs_to_delete = []
        for plan in plans:
            to_delete.extend(plan.products)
            for line in plan.costs:
                if line.type in types:
                    costs_to_delete.append(line)

        if to_delete:
            ProductLines.delete(to_delete)
        if costs_to_delete:
            with Transaction().set_context(reset_costs=True):
                CostLines.delete(costs_to_delete)

    @classmethod
    @ModelView.button
    @Workflow.transition('computed')
    def compute(cls, plans):
        pool = Pool()
        ProductLines = pool.get('product.cost.plan.product_line')
        CostLines = pool.get('product.cost.plan.cost')

        to_create = []
        for plan in plans:
            if plan.product and plan.bom:
                to_create.extend(plan.explode_bom(plan.product, plan.bom,
                        plan.quantity, plan.product.default_uom))
        if to_create:
            ProductLines.create(to_create)

        costs_to_create = []
        for plan in plans:
            costs_to_create.extend(plan.get_costs())
        if costs_to_create:
            CostLines.create(costs_to_create)

    def get_costs(self):
        " Returns the cost lines to be created on compute "
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
        " Returns products for the especified products"
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
        Input = pool.get('production.bom.input')
        quantity = Input.compute_quantity(input_, factor)
        return {
            'product': input_.product.id,
            'quantity': quantity,
            'uom': input_.uom.id,
            'product_cost_price': input_.product.cost_price,
            'cost_price': input_.product.cost_price,
        }


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

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    product = fields.Many2One('product.product', 'Product',
        domain=[
            ('type', '!=', 'service'),
        ], on_change=['product', 'uom'])
    quantity = fields.Float('Quantity', required=True)
    uom_category = fields.Function(fields.Many2One(
        'product.uom.category', 'Uom Category',
        on_change_with=['product']), 'on_change_with_uom_category')
    uom = fields.Many2One('product.uom', 'Uom', required=True,
        domain=[
            If(Bool(Eval('product', 0)),
            ('category', '=', Eval('uom_category')),
            ('id', '!=', 0),
            )
        ], depends=['uom_category'])
    product_cost_price = fields.Numeric('Product Cost Price',
        states={
            'readonly': True,
            }, depends=['product'])
    last_purchase_price = fields.Numeric('Last Purchase Price', states={
            'readonly': True,
            }, depends=['product'])
    cost_price = fields.Numeric('Cost Price', required=True)
    total = fields.Function(fields.Numeric('Total Cost', on_change_with=[
                'quantity', 'cost_price', 'uom', 'product']),
        'on_change_with_total')

    def on_change_product(self):
        res = {}
        if self.product:
            uoms = self.product.default_uom.category.uoms
            if (not self.uom or self.uom not in uoms):
                # TODO: Convert price to UoM
                res['uom'] = self.product.default_uom.id
                res['uom.rec_name'] = self.product.default_uom.rec_name
                res['product_cost_price'] = self.product.cost_price
		res['cost_price'] = self.product.cost_price
        else:
            res['uom'] = None
            res['uom.rec_name'] = ''
            res['product_cost_price'] = None
        return res

    def on_change_with_uom_category(self, name=None):
        if self.product:
            return self.product.default_uom.category.id

    def on_change_with_total(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
	quantity = self.quantity
        if self.product:
            # TODO: Once converted prices to line's UoM, do not do the following
            # conversion
            quantity = Uom.compute_qty(self.uom, self.quantity,
                self.product.default_uom, round=False)
        if not quantity:
            return Decimal('0.0')
        return Decimal(str(quantity)) * (self.cost_price or Decimal('0.0'))

STATES = {
    'readonly': Eval('system', False),
    }
DEPENDS = ['system']


class PlanCost(ModelSQL, ModelView):
    'Plan Cost'
    __name__ = 'product.cost.plan.cost'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    type = fields.Many2One('product.cost.plan.cost.type', 'Type',
        required=True, states=STATES, depends=DEPENDS)
    cost = fields.Numeric('Cost', required=True, states=STATES,
        depends=DEPENDS)
    system = fields.Boolean('System Managed', readonly=True)

    @classmethod
    def __setup__(cls):
        super(PlanCost, cls).__setup__()
        cls._error_messages.update({
                'delete_system_cost': ('You can not delete cost "%s" '
                    'because it\'s managed by system.'),
                })

    @staticmethod
    def default_system():
        return False

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
                    cls.raise_user_error('delete_system_cost',
                        cost.rec_name)
        super(PlanCost, cls).delete(costs)

    def update_cost_values(self, value):
        return {'cost': value, 'id': self.id}
