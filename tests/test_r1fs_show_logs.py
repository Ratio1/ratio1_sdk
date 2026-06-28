import unittest

from ratio1.ipfs.r1fs import R1FSEngine


class R1FSShowLogsTests(unittest.TestCase):

  def _engine(self):
    engine = object.__new__(R1FSEngine)
    engine.messages = []
    engine.debug_messages = []
    engine.add_file_show_logs = []
    engine.calculate_file_cid_show_logs = []

    def P(message, *args, **kwargs):
      engine.messages.append(str(message))

    def Pd(message, *args, **kwargs):
      engine.debug_messages.append(str(message))

    def add_file(**kwargs):
      engine.add_file_show_logs.append(kwargs.get("show_logs"))
      return "cid"

    def calculate_file_cid(**kwargs):
      engine.calculate_file_cid_show_logs.append(kwargs.get("show_logs"))
      return "cid"

    engine.P = P
    engine.Pd = Pd
    engine.add_file = add_file
    engine.calculate_file_cid = calculate_file_cid
    return engine

  def test_add_json_suppresses_raw_json_when_show_logs_false(self):
    engine = self._engine()

    cid = engine.add_json({"CRDB_PASSWORD": "secret"}, nonce=1, show_logs=False)

    self.assertEqual(cid, "cid")
    self.assertEqual(engine.add_file_show_logs, [False])
    self.assertEqual(engine.messages, [])
    self.assertEqual(engine.debug_messages, [])

  def test_calculate_json_cid_suppresses_raw_json_when_show_logs_false(self):
    engine = self._engine()

    cid = engine.calculate_json_cid({"CRDB_PASSWORD": "secret"}, nonce=1, show_logs=False)

    self.assertEqual(cid, "cid")
    self.assertEqual(engine.calculate_file_cid_show_logs, [False])
    self.assertEqual(engine.messages, [])
    self.assertEqual(engine.debug_messages, [])


if __name__ == "__main__":
  unittest.main()
