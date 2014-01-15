from decimal import Decimal
from trytond.model import Workflow, ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval, Bool

__all__ = ['Plan', 'PlanBOM', 'PlanProductLine']


class Plan(Workflow, ModelSQL, ModelView):
    'Product Cost Plan'
    __name__ = 'product.cost.plan'

    product = fields.Many2One('product.product', 'Product', required=True,
        states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'], on_change=['product', 'bom', 'boms'])
    bom = fields.Many2One('production.bom', 'BOM', on_change_with=['product'],
        required=True, states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state', 'product'],
        domain=[
            ('output_products', '=', Eval('product', 0)),
            ],)
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
            }, depends=['state'])
    product_cost = fields.Function(fields.Numeric('Product Cost',
            on_change_with=['products']), 'on_change_with_product_cost')
    total_cost = fields.Function(fields.Numeric('Total Cost',
            on_change_with=['product_cost']),
        'on_change_with_total_cost')
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

    def on_change_with_product_cost(self, name=None):
        cost = Decimal('0.0')
        for line in self.products:
            cost += line.total
        return cost

    def on_change_with_total_cost(self, name=None):
        return self.product_cost

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def reset(cls, plans):
        pool = Pool()
        ProductLines = pool.get('product.cost.plan.product_line')

        to_delete = []
        for plan in plans:
            to_delete.extend(plan.products)

        if to_delete:
            ProductLines.delete(to_delete)

    @classmethod
    @ModelView.button
    @Workflow.transition('computed')
    def compute(cls, plans):
        pool = Pool()
        ProductLines = pool.get('product.cost.plan.product_line')

        to_create = []
        for plan in plans:
            to_create.extend(plan.explode_bom(plan.product, plan.bom,
                    plan.quantity, plan.product.default_uom))
        if to_create:
            ProductLines.create(to_create)

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

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True)
    product = fields.Many2One('product.product', 'Product', required=True)
    bom = fields.Many2One('production.bom', 'BOM', domain=[
            ('output_products', '=', Eval('product', 0)),
            ], depends=['product'])


class PlanProductLine(ModelSQL, ModelView):
    'Product Cost Plan Product Line'
    __name__ = 'product.cost.plan.product_line'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True)
    product = fields.Many2One('product.product', 'Product', required=True,
        domain=[
            ('type', '!=', 'service'),
        ], on_change=['product', 'uom'])
    quantity = fields.Float('Quantity', required=True)
    uom_category = fields.Function(fields.Many2One(
        'product.uom.category', 'Uom Category',
        on_change_with=['product']), 'on_change_with_uom_category')
    uom = fields.Many2One('product.uom', 'Uom', required=True,
        domain=[
            ('category', '=', Eval('uom_category')),
        ], depends=['uom_category'])
    product_cost_price = fields.Numeric('Product Cost Price', required=True,
        states={
            'readonly': Bool(Eval('product', 0)),
            }, depends=['product'])
    last_purchase_price = fields.Numeric('Last Purchase Price', states={
            'readonly': Bool(Eval('product', 0)),
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
                res['uom'] = self.product.default_uom.id
                res['uom.rec_name'] = self.product.default_uom.rec_name
                res['product_cost_price'] = self.product.cost_price
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
        if not self.product:
            return Decimal('0.0')
        quantity = Uom.compute_qty(self.uom, self.quantity,
            self.product.default_uom, round=False)

        return Decimal(str(quantity)) * (self.cost_price or Decimal('0.0'))
