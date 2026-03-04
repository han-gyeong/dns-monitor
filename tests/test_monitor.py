from app.monitor import DNSMonitorService


class FakeRecord:
    def __init__(self, priority, exchange=None, ipv4=None):
        self.preference = priority
        self.exchange = exchange
        self.ipv4 = ipv4

    def __str__(self):
        return self.ipv4


def test_detect_changes_mx_and_a():
    monitor = DNSMonitorService()

    class S:
        def __init__(self, mx, a):
            self.mx_records = mx
            self.mx_a_records = a

    class MX:
        def __init__(self, priority, exchange):
            self.priority = priority
            self.exchange = exchange

    class A:
        def __init__(self, exchange, ipv4):
            self.exchange = exchange
            self.ipv4 = ipv4

    prev = S([MX(10, "mx1.example.com")], [A("mx1.example.com", "1.1.1.1")])
    curr = S([MX(10, "mx2.example.com")], [A("mx2.example.com", "2.2.2.2")])

    changes = monitor.detect_changes(prev, curr)

    assert len(changes) == 2
    types = {c[0] for c in changes}
    assert "MX_CHANGED" in types
    assert "A_CHANGED" in types
