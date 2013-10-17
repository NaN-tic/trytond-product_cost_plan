from decimal import Decimal
from trytond.model import Workflow, ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval

__all__ = ['Plan', 'PlanBOM', 'PlanProductLine']


class Plan(Workflow, ModelSQL, ModelView):
    'Product Cost Plan'
    __name__ = 'product.cost.plan'
    product = fields.Many2One('product.product', 'Product', required=True)
    bom = fields.Many2One('production.bom', 'BOM', on_change_with=['product'],
        required=True)
    boms = fields.One2Many('product.cost.plan.bom', 'plan', 'BOMs', states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'], on_change_with=['bom'])
    quantity = fields.Float('Quantity', required=True)
    products = fields.One2Many('product.cost.plan.product_line', 'plan',
        'Products', states={
            'readonly': Eval('state') == 'draft',
            }, depends=['state'])
    product_cost = fields.Function(fields.Numeric('Product Cost',
            on_change_with=['products']), 'on_change_with_product_cost')
    total_cost = fields.Function(fields.Numeric('Total Cost',
            on_change_with=['products']),
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
                'confirm': {
                    'invisible': Eval('state') == 'confirmed',
                    },
                'reset': {
                    'invisible': Eval('state') == 'draft',
                    }
                })

    @staticmethod
    def default_state():
        return 'draft'

    def on_change_with_bom(self):
        BOM = Pool().get('production.bom')
        product_id = self.product.id if self.product else None
        boms = BOM.search([('output_products', '=', product_id)])
        if boms:
            return boms[0].id
        return None

    def on_change_with_boms(self):
        return []

    def on_change_with_product_cost(self, name=None):
        cost = Decimal('0.0')
        for line in self.products:
            cost += line.total
        return cost

    def on_change_with_total_cost(self, name=None):
        return self.product_cost

    @classmethod
    @ModelView.button
    @Workflow.transition('confirmed')
    def compute(cls, plans):
         '''
         Create all necessary products and operations
         '''
         pass


class PlanBOM(ModelSQL, ModelView):
    'Product Cost Plan BOM'
    __name__ = 'product.cost.plan.bom'
    plan = fields.Many2One('product.cost.plan', 'Plan', required=True)
    product = fields.Many2One('product.product', 'Product', required=True)
    bom = fields.Many2One('production.bom', 'BOM')


class PlanProductLine(ModelSQL, ModelView):
    'Product Cost Plan Product Line'
    __name__ = 'product.cost.plan.product_line'
    plan = fields.Many2One('product.cost.plan', 'Plan', required=True)
    product = fields.Many2One('product.product', 'Product', required=True)
    quantity = fields.Float('Quantity', required=True)
    product_cost_price = fields.Numeric('Product Cost Price', required=True)
    last_purchase_price = fields.Numeric('Last Purchase Price')
    cost_price = fields.Numeric('Cost Price', required=True)
    total = fields.Function(fields.Numeric('Total Cost', on_change_with=[
                'quantity', 'cost_price']), 'on_change_with_total')

    def on_change_with_total(self):
        return ((self.quantity or Decimal('0.0'))
            * (self.cost_price or Decimal('0.0')))
