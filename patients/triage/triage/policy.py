"""Support policy. This is the source of truth the agent must follow."""

QUEUES = ("billing", "technical", "account", "sales")

PRIORITY_POLICY = """\
P1: production outage or data loss for an enterprise customer.
P2: any other ticket from an enterprise customer (including sales and billing), a production outage
    for a pro customer, or a past_due account that cannot pay.
P3: everything else: pro or free billing and how-to questions, and sales enquiries from
    non-enterprise customers."""
