"""A stalled GUI must not block the application's event入口."""
import subprocess
import sys
import unittest


class GuiWakeTests(unittest.TestCase):
    def test_saturated_wake_does_not_block_events_status_or_stop(self):
        script = '''
from codex_pet.daemon import Daemon
instance = Daemon()
try:
    for _ in range(20000):
        instance.gui.wake()
    for state in ('running', 'needs_input', 'ready'):
        result = instance.process({'action':'event', 'event':{'state':state, 'session_id':'test'}})
        assert result['applied'] and result['state'] == state
    assert instance.process({'action':'status'})['state'] == 'ready'
    assert instance.process({'action':'reconnect'})['ok']
    assert instance.process({'action':'stop'})['ok']
finally:
    instance.gui.stop()
    instance.signal_read.close()
    instance.signal_write.close()
'''
        result = subprocess.run([sys.executable, '-c', script],
                                text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
