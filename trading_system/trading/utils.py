from django.db import transaction
from django.utils import timezone
from .models import Order, Trade

def match_order(new_order):
    # Begin a transaction to ensure atomicity
    with transaction.atomic():
        # For a BUY limit order, we are looking for SELL orders at the same price or lower
        if new_order.order_type == 'BUY' and new_order.order_mode == 'LIMIT':
            opposite_orders = Order.objects.filter(
                order_type='SELL', 
                order_mode='LIMIT', 
                # price__lte=new_order.price, 
                is_matched=False
            ).order_by('price', 'timestamp')
        
        # For a SELL limit order, we are looking for BUY orders at the same price or higher
        elif new_order.order_type == 'SELL' and new_order.order_mode == 'LIMIT':
            opposite_orders = Order.objects.filter(
                order_type='BUY', 
                order_mode='LIMIT', 
                # price__gte=new_order.price, 
                is_matched=False
            ).order_by('-price', 'timestamp')

        # For a BUY market order, we are looking for SELL orders with the lowest price
        elif new_order.order_type == 'BUY' and new_order.order_mode == 'MARKET':
            opposite_orders = Order.objects.filter(
                order_type='SELL', 
                is_matched=False
            ).order_by('price', 'timestamp')

        # For a SELL market order, we are looking for BUY orders with the highest price
        elif new_order.order_type == 'SELL' and new_order.order_mode == 'MARKET':
            opposite_orders = Order.objects.filter(
                order_type='BUY', 
                is_matched=False
            ).order_by('-price', 'timestamp')

        # Try to match with the opposite orders
        remaining_quantity = new_order.quantity
        for opposite_order in opposite_orders:
            if remaining_quantity <= 0:
                break
            
            match_quantity = min(remaining_quantity, opposite_order.quantity)

            # For limit orders, the price is already set in the opposite order
            if new_order.order_mode == 'LIMIT':
                match_price = opposite_order.price
            # For market orders, the price is taken from the best available order
            else:
                match_price = opposite_order.price

            # Create a trade entry for the matched orders
            Trade.objects.create(
                buyer=new_order.user if new_order.order_type == 'BUY' else opposite_order.user,
                seller=opposite_order.user if new_order.order_type == 'BUY' else new_order.user,
                quantity=match_quantity,
                price=match_price,
                timestamp=timezone.now()
            )

            # Update the quantities of the matched orders
            remaining_quantity -= match_quantity
            opposite_order.quantity -= match_quantity
            new_order.quantity -= match_quantity
            opposite_order.save()
            new_order.save()

            # If the opposite order is fully matched, mark it as matched
            if opposite_order.quantity == 0:
                opposite_order.is_matched = True
                opposite_order.save()

            # If the new order is fully matched, mark it as matched
            if new_order.quantity == 0:
                new_order.is_matched = True
                new_order.save()

        # If the new order is partially matched, update its quantity and status
        if new_order.quantity > 0:
            new_order.save()
        else:
            new_order.is_matched = True
            new_order.save()

        # Ensure that any remaining unmatched orders are still available for future matches
        new_order.timestamp = timezone.now()
        new_order.save()
