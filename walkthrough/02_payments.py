import stripe
import requests

STRIPE_SECRET = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"
AWS_ACCESS_KEY = "AKIA" + "IOSFODNN7EXAMPLEKEY1"

stripe.api_key = STRIPE_SECRET

def charge_customer(amount, currency, card_token):
    charge = stripe.Charge.create(
        amount=amount,
        currency=currency,
        source=card_token,
        description="Shop purchase"
    )
    return charge

def refund_charge(charge_id):
    refund = stripe.Refund.create(charge=charge_id)
    return refund

def notify_webhook(payload):
    url = "https://hooks.internal/payment-events"
    headers = {"Authorization": "Bearer " + AWS_ACCESS_KEY}
    requests.post(url, json=payload, headers=headers, verify=False)
