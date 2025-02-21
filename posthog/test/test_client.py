import time
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import mock
import six

from posthog.client import Client
from posthog.test.test_utils import FAKE_TEST_API_KEY
from posthog.version import VERSION


class TestClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This ensures no real HTTP POST requests are made
        cls.client_post_patcher = mock.patch("posthog.client.batch_post")
        cls.consumer_post_patcher = mock.patch("posthog.consumer.batch_post")
        cls.client_post_patcher.start()
        cls.consumer_post_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.client_post_patcher.stop()
        cls.consumer_post_patcher.stop()

    def set_fail(self, e, batch):
        """Mark the failure handler"""
        print("FAIL", e, batch)
        self.failed = True

    def setUp(self):
        self.failed = False
        self.client = Client(FAKE_TEST_API_KEY, on_error=self.set_fail)

    def test_requires_api_key(self):
        self.assertRaises(AssertionError, Client)

    def test_empty_flush(self):
        self.client.flush()

    def test_basic_capture(self):
        client = self.client
        success, msg = client.capture("distinct_id", "python test event")
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["event"], "python test event")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))
        self.assertEqual(msg["distinct_id"], "distinct_id")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)

    def test_basic_capture_with_uuid(self):
        client = self.client
        uuid = str(uuid4())
        success, msg = client.capture("distinct_id", "python test event", uuid=uuid)
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["event"], "python test event")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertEqual(msg["uuid"], uuid)
        self.assertEqual(msg["distinct_id"], "distinct_id")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)

    def test_basic_capture_with_project_api_key(self):

        client = Client(project_api_key=FAKE_TEST_API_KEY, on_error=self.set_fail)

        success, msg = client.capture("distinct_id", "python test event")
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["event"], "python test event")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))
        self.assertEqual(msg["distinct_id"], "distinct_id")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)

    @mock.patch("posthog.client.decide")
    def test_basic_capture_with_feature_flags(self, patch_decide):
        patch_decide.return_value = {"featureFlags": {"beta-feature": "random-variant"}}

        client = Client(FAKE_TEST_API_KEY, on_error=self.set_fail, personal_api_key=FAKE_TEST_API_KEY)
        success, msg = client.capture("distinct_id", "python test event", send_feature_flags=True)
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["event"], "python test event")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))
        self.assertEqual(msg["distinct_id"], "distinct_id")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)
        self.assertEqual(msg["properties"]["$feature/beta-feature"], "random-variant")
        self.assertEqual(msg["properties"]["$active_feature_flags"], ["beta-feature"])

        self.assertEqual(patch_decide.call_count, 1)

    @mock.patch("posthog.client.decide")
    def test_basic_capture_with_feature_flags_switched_off_doesnt_send_them(self, patch_decide):
        patch_decide.return_value = {"featureFlags": {"beta-feature": "random-variant"}}

        client = Client(FAKE_TEST_API_KEY, on_error=self.set_fail, personal_api_key=FAKE_TEST_API_KEY)
        success, msg = client.capture("distinct_id", "python test event", send_feature_flags=False)
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["event"], "python test event")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))
        self.assertEqual(msg["distinct_id"], "distinct_id")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)
        self.assertTrue("$feature/beta-feature" not in msg["properties"])
        self.assertTrue("$active_feature_flags" not in msg["properties"])

        self.assertEqual(patch_decide.call_count, 0)

    def test_stringifies_distinct_id(self):
        # A large number that loses precision in node:
        # node -e "console.log(157963456373623802 + 1)" > 157963456373623800
        client = self.client
        success, msg = client.capture(distinct_id=157963456373623802, event="python test event")
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["distinct_id"], "157963456373623802")

    def test_advanced_capture(self):
        client = self.client
        success, msg = client.capture(
            "distinct_id",
            "python test event",
            {"property": "value"},
            {"ip": "192.168.0.1"},
            datetime(2014, 9, 3),
            "new-uuid",
        )

        self.assertTrue(success)

        self.assertEqual(msg["timestamp"], "2014-09-03T00:00:00+00:00")
        self.assertEqual(msg["properties"]["property"], "value")
        self.assertEqual(msg["context"]["ip"], "192.168.0.1")
        self.assertEqual(msg["event"], "python test event")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)
        self.assertEqual(msg["uuid"], "new-uuid")
        self.assertEqual(msg["distinct_id"], "distinct_id")
        self.assertTrue("$groups" not in msg["properties"])

    def test_groups_capture(self):
        success, msg = self.client.capture(
            "distinct_id",
            "test_event",
            groups={"company": "id:5", "instance": "app.posthog.com"},
        )

        self.assertTrue(success)
        self.assertEqual(msg["properties"]["$groups"], {"company": "id:5", "instance": "app.posthog.com"})

    def test_basic_identify(self):
        client = self.client
        success, msg = client.identify("distinct_id", {"trait": "value"})
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["$set"]["trait"], "value")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))
        self.assertEqual(msg["distinct_id"], "distinct_id")

    def test_advanced_identify(self):
        client = self.client
        success, msg = client.identify(
            "distinct_id", {"trait": "value"}, {"ip": "192.168.0.1"}, datetime(2014, 9, 3), "new-uuid"
        )

        self.assertTrue(success)

        self.assertEqual(msg["timestamp"], "2014-09-03T00:00:00+00:00")
        self.assertEqual(msg["context"]["ip"], "192.168.0.1")
        self.assertEqual(msg["$set"]["trait"], "value")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertEqual(msg["uuid"], "new-uuid")
        self.assertEqual(msg["distinct_id"], "distinct_id")

    def test_basic_set(self):
        client = self.client
        success, msg = client.set("distinct_id", {"trait": "value"})
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["$set"]["trait"], "value")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))
        self.assertEqual(msg["distinct_id"], "distinct_id")

    def test_advanced_set(self):
        client = self.client
        success, msg = client.set(
            "distinct_id", {"trait": "value"}, {"ip": "192.168.0.1"}, datetime(2014, 9, 3), "new-uuid"
        )

        self.assertTrue(success)

        self.assertEqual(msg["timestamp"], "2014-09-03T00:00:00+00:00")
        self.assertEqual(msg["context"]["ip"], "192.168.0.1")
        self.assertEqual(msg["$set"]["trait"], "value")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertEqual(msg["uuid"], "new-uuid")
        self.assertEqual(msg["distinct_id"], "distinct_id")

    def test_basic_set_once(self):
        client = self.client
        success, msg = client.set_once("distinct_id", {"trait": "value"})
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)

        self.assertEqual(msg["$set_once"]["trait"], "value")
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))
        self.assertEqual(msg["distinct_id"], "distinct_id")

    def test_advanced_set_once(self):
        client = self.client
        success, msg = client.set_once(
            "distinct_id", {"trait": "value"}, {"ip": "192.168.0.1"}, datetime(2014, 9, 3), "new-uuid"
        )

        self.assertTrue(success)

        self.assertEqual(msg["timestamp"], "2014-09-03T00:00:00+00:00")
        self.assertEqual(msg["context"]["ip"], "192.168.0.1")
        self.assertEqual(msg["$set_once"]["trait"], "value")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertEqual(msg["uuid"], "new-uuid")
        self.assertEqual(msg["distinct_id"], "distinct_id")

    def test_basic_group_identify(self):
        success, msg = self.client.group_identify("organization", "id:5")

        self.assertTrue(success)
        self.assertEqual(msg["event"], "$groupidentify")
        self.assertEqual(msg["distinct_id"], "$organization_id:5")
        self.assertEqual(
            msg["properties"],
            {
                "$group_type": "organization",
                "$group_key": "id:5",
                "$group_set": {},
                "$lib": "posthog-python",
                "$lib_version": VERSION,
            },
        )
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertIsNone(msg.get("uuid"))

    def test_advanced_group_identify(self):
        success, msg = self.client.group_identify(
            "organization", "id:5", {"trait": "value"}, {"ip": "192.168.0.1"}, datetime(2014, 9, 3), "new-uuid"
        )

        self.assertTrue(success)
        self.assertEqual(msg["event"], "$groupidentify")
        self.assertEqual(msg["distinct_id"], "$organization_id:5")
        self.assertEqual(
            msg["properties"],
            {
                "$group_type": "organization",
                "$group_key": "id:5",
                "$group_set": {"trait": "value"},
                "$lib": "posthog-python",
                "$lib_version": VERSION,
            },
        )
        self.assertEqual(msg["timestamp"], "2014-09-03T00:00:00+00:00")
        self.assertEqual(msg["context"]["ip"], "192.168.0.1")

    def test_basic_alias(self):
        client = self.client
        success, msg = client.alias("previousId", "distinct_id")
        client.flush()
        self.assertTrue(success)
        self.assertFalse(self.failed)
        self.assertEqual(msg["properties"]["distinct_id"], "previousId")
        self.assertEqual(msg["properties"]["alias"], "distinct_id")

    def test_basic_page(self):
        client = self.client
        success, msg = client.page("distinct_id", url="https://posthog.com/contact")
        self.assertFalse(self.failed)
        client.flush()
        self.assertTrue(success)
        self.assertEqual(msg["distinct_id"], "distinct_id")
        self.assertEqual(msg["properties"]["$current_url"], "https://posthog.com/contact")

    def test_basic_page_distinct_uuid(self):
        client = self.client
        distinct_id = uuid4()
        success, msg = client.page(distinct_id, url="https://posthog.com/contact")
        self.assertFalse(self.failed)
        client.flush()
        self.assertTrue(success)
        self.assertEqual(msg["distinct_id"], str(distinct_id))
        self.assertEqual(msg["properties"]["$current_url"], "https://posthog.com/contact")

    def test_advanced_page(self):
        client = self.client
        success, msg = client.page(
            "distinct_id",
            "https://posthog.com/contact",
            {"property": "value"},
            {"ip": "192.168.0.1"},
            datetime(2014, 9, 3),
            "new-uuid",
        )

        self.assertTrue(success)

        self.assertEqual(msg["timestamp"], "2014-09-03T00:00:00+00:00")
        self.assertEqual(msg["context"]["ip"], "192.168.0.1")
        self.assertEqual(msg["properties"]["$current_url"], "https://posthog.com/contact")
        self.assertEqual(msg["properties"]["property"], "value")
        self.assertEqual(msg["properties"]["$lib"], "posthog-python")
        self.assertEqual(msg["properties"]["$lib_version"], VERSION)
        self.assertTrue(isinstance(msg["timestamp"], str))
        self.assertEqual(msg["uuid"], "new-uuid")
        self.assertEqual(msg["distinct_id"], "distinct_id")

    def test_flush(self):
        client = self.client
        # set up the consumer with more requests than a single batch will allow
        for i in range(1000):
            success, msg = client.identify("distinct_id", {"trait": "value"})
        # We can't reliably assert that the queue is non-empty here; that's
        # a race condition. We do our best to load it up though.
        client.flush()
        # Make sure that the client queue is empty after flushing
        self.assertTrue(client.queue.empty())

    def test_shutdown(self):
        client = self.client
        # set up the consumer with more requests than a single batch will allow
        for i in range(1000):
            success, msg = client.identify("distinct_id", {"trait": "value"})
        client.shutdown()
        # we expect two things after shutdown:
        # 1. client queue is empty
        # 2. consumer thread has stopped
        self.assertTrue(client.queue.empty())
        for consumer in client.consumers:
            self.assertFalse(consumer.is_alive())

    def test_synchronous(self):
        client = Client(FAKE_TEST_API_KEY, sync_mode=True)

        success, message = client.identify("distinct_id")
        self.assertFalse(client.consumers)
        self.assertTrue(client.queue.empty())
        self.assertTrue(success)

    def test_overflow(self):
        client = Client(FAKE_TEST_API_KEY, max_queue_size=1)
        # Ensure consumer thread is no longer uploading
        client.join()

        for i in range(10):
            client.identify("distinct_id")

        success, msg = client.identify("distinct_id")
        # Make sure we are informed that the queue is at capacity
        self.assertFalse(success)

    def test_unicode(self):
        Client(six.u("unicode_key"))

    def test_numeric_distinct_id(self):
        self.client.capture(1234, "python event")
        self.client.flush()
        self.assertFalse(self.failed)

    def test_debug(self):
        Client("bad_key", debug=True)

    def test_gzip(self):
        client = Client(FAKE_TEST_API_KEY, on_error=self.fail, gzip=True)
        for _ in range(10):
            client.identify("distinct_id", {"trait": "value"})
        client.flush()
        self.assertFalse(self.failed)

    def test_user_defined_flush_at(self):
        client = Client(FAKE_TEST_API_KEY, on_error=self.fail, flush_at=10, flush_interval=3)

        def mock_post_fn(*args, **kwargs):
            self.assertEqual(len(kwargs["batch"]), 10)

        # the post function should be called 2 times, with a batch size of 10
        # each time.
        with mock.patch("posthog.consumer.batch_post", side_effect=mock_post_fn) as mock_post:
            for _ in range(20):
                client.identify("distinct_id", {"trait": "value"})
            time.sleep(1)
            self.assertEqual(mock_post.call_count, 2)

    def test_user_defined_timeout(self):
        client = Client(FAKE_TEST_API_KEY, timeout=10)
        for consumer in client.consumers:
            self.assertEqual(consumer.timeout, 10)

    def test_default_timeout_15(self):
        client = Client(FAKE_TEST_API_KEY)
        for consumer in client.consumers:
            self.assertEqual(consumer.timeout, 15)

    @mock.patch("posthog.client.Poller")
    @mock.patch("posthog.client.get")
    def test_call_identify_fails(self, patch_get, patch_poll):
        def raise_effect():
            raise Exception("http exception")

        patch_get.return_value.raiseError.side_effect = raise_effect
        client = Client(FAKE_TEST_API_KEY, personal_api_key="test")
        client.feature_flags = [{"key": "example", "is_simple_flag": False}]

        self.assertFalse(client.feature_enabled("example", "distinct_id"))
