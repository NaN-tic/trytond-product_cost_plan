# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal

from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.model import ModelSQL, ModelView, fields
from trytond.modules.product import price_digits, round_price
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If

_ZERO = Decimal(0)


class PlanOperationLine(ModelSQL, ModelView):
    'Product Cost Plan Operation Line'
    __name__ = 'product.cost.plan.step_line'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    name = fields.Char('Name')
    operation = fields.Many2One('production.routing.operation', 'Operation',
        domain=[
            If(Bool(Eval('work_center_category')),
                ('work_center_category', '=', Eval('work_center_category')),
                ()),
            ],
        depends=['work_center_category'])
    work_center_category = fields.Many2One('production.work.center.category',
        'Work Center Category', states={
            'readonly': Bool(Eval('operation')) | Bool(Eval('work_center')),
            }, depends=['operation', 'work_center'])
    work_center = fields.Many2One('production.work.center', 'Work Center',
        domain=[
            If(Bool(Eval('work_center_category')),
                ('category', '=', Eval('work_center_category')),
                ()),
            ],
        depends=['work_center_category'])
    cost_price = fields.Numeric('Cost Price', required=True,
        digits=price_digits)
    calculation = fields.Selection([
            ('standard', 'Standard'),
            ('fixed', 'Fixed'),
            ], 'Calculation', required=True,
        help='Use Standard to multiply the amount of time by the number of '
        'units produced. Use Fixed to use the indicated time once for the '
        'full plan quantity.')
    cost_method = fields.Selection([
            ('hour', 'Per Hour'),
            ('cycle', 'Per Cycle'),
            ], 'Cost Method', required=True, states={
            'invisible': Eval('calculation') == 'fixed',
            }, depends=['calculation'])
    time = fields.TimeDelta('Time', required=True)
    quantity_digits = fields.Function(fields.Integer('Quantity Digits'),
        'on_change_with_quantity_digits')
    quantity = fields.Float('Quantity',
        digits=(16, Eval('quantity_digits', 2)),
        states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            },
        depends=['calculation', 'quantity_digits'],
        help='Quantity of the plan product processed by the specified time.')
    unit_cost = fields.Function(fields.Numeric('Unit Cost',
            digits=price_digits,
            help="The cost of this operation for each unit of plan's "
            "product."),
        'get_unit_cost')
    total_cost = fields.Function(fields.Numeric('Total Cost',
            digits=price_digits,
            help="The cost of this operation for total plan's quantity."),
        'get_total_cost')

    @staticmethod
    def default_calculation():
        return 'standard'

    @staticmethod
    def default_cost_method():
        return 'hour'

    @fields.depends('plan', '_parent_plan.uom')
    def on_change_with_quantity_digits(self, name=None):
        if self.plan and self.plan.uom:
            return self.plan.uom.digits
        return 2

    @fields.depends('operation', 'work_center_category', 'work_center')
    def on_change_work_center_category(self):
        if (self.operation and self.operation.work_center_category
                != self.work_center_category):
            self.operation = None
        if (self.work_center and self.work_center.category
                != self.work_center_category):
            self.work_center = None

    @fields.depends('operation', 'work_center', 'work_center_category')
    def on_change_operation(self):
        if self.operation:
            self.work_center_category = self.operation.work_center_category
            if (self.work_center and self.work_center.category
                    != self.work_center_category):
                self.work_center = None

    @fields.depends('cost_method', 'cost_price', 'operation', 'work_center',
        'work_center_category')
    def on_change_work_center(self):
        if (not self.operation and self.work_center
                and self.work_center.category):
            self.work_center_category = self.work_center.category
        if self.work_center and self.work_center.cost_method:
            self.cost_method = self.work_center.cost_method
        if self.work_center and not self.cost_price:
            if getattr(self.work_center, 'cost_price', None):
                self.cost_price = self.work_center.cost_price

    def get_unit_cost(self, name=None):
        unit_cost = self.get_total_cost(None, round=False)
        if unit_cost and self.plan and self.plan.quantity:
            unit_cost /= Decimal(str(self.plan.quantity))
        return round_price(unit_cost or _ZERO)

    def get_total_cost(self, name=None, round=True):
        if not self.cost_price:
            return _ZERO
        if not self.plan or not self.plan.quantity:
            return _ZERO
        if self.calculation == 'standard' and not self.quantity:
            return _ZERO

        if self.calculation == 'standard':
            if not self.quantity:
                return _ZERO
            factor = Decimal(str(self.plan.quantity / self.quantity))
        else:
            factor = Decimal(1)

        if self.cost_method == 'cycle':
            total_cost = self.cost_price * factor
        else:
            if not self.time:
                return _ZERO
            hours = Decimal(str(self.time.total_seconds())) / Decimal('3600')
            total_cost = hours * self.cost_price * factor

        if not round:
            return total_cost
        return round_price(total_cost or _ZERO)

    @classmethod
    def validate(cls, lines):
        super().validate(lines)


class Plan(metaclass=PoolMeta):
    __name__ = 'product.cost.plan'

    operations = fields.One2Many('product.cost.plan.step_line', 'plan',
        'Operations')
    operations_cost = fields.Function(fields.Numeric('Operations Cost',
            digits=price_digits),
        'get_operations_cost')

    def create_bom(self, name):
        if self.operations:
            self._check_routing_step_lines()
        bom = super().create_bom(name)
        if self.operations:
            self._create_routing(name, bom)
        return bom

    def get_operations_cost(self, name):
        if not self.quantity:
            return Decimal(0)
        cost = sum(o.get_total_cost(None, round=False) for o in self.operations)
        cost /= Decimal(str(self.quantity))
        return round_price(cost)

    def _check_routing_step_lines(self):
        for step_line in self.operations:
            if not (step_line.operation and step_line.calculation
                    and step_line.time):
                raise UserError(gettext(
                        'product_cost_plan.'
                        'msg_step_lines_missing_routing_information',
                        plan=self.rec_name))

    def _create_routing(self, name, bom):
        pool = Pool()
        ProductBOM = pool.get('product.product-production.bom')
        Routing = pool.get('production.routing')
        RoutingBOM = pool.get('production.routing-production.bom')

        routing, = Routing.create([{
                    'name': name,
                    'steps': [('create', [self._get_routing_step(step_line)
                                for step_line in self.operations])],
                    }])
        RoutingBOM.create([{
                    'routing': routing.id,
                    'bom': bom.id,
                    }])
        product_boms = ProductBOM.search([
                ('product', '=', self.product.id),
                ('bom', '=', bom.id),
                ], limit=1)
        if product_boms:
            ProductBOM.write(product_boms, {
                    'routing': routing.id,
                    })
        return routing

    def _get_routing_step(self, step_line):
        return {
            'operation': step_line.operation.id,
            'calculation': step_line.calculation,
            'time': step_line.time,
            }


class ProductBom(metaclass=PoolMeta):
    __name__ = 'product.product-production.bom'

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        new_args = []
        for product_boms, values in zip(actions, actions):
            values = values.copy()
            if 'bom' in values and 'routing' not in values:
                # Reset stale routing when the BOM is replaced so the
                # production_routing domain remains valid during the write.
                values['routing'] = None
            new_args.extend((product_boms, values))
        super().write(*new_args)
