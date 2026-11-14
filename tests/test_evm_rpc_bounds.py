"""Offline checks of the limits the SDK sets on its RPC client: seconds per request, tries per call, chain id reads."""
# The RPC requests and answers are JSON.
import json
# The engine's network is chosen through an environment key.
import os
# The test runner.
import unittest
# The engine's first-check flags are a dict with a default.
from collections import defaultdict
# The genesis date the logger stand-in returns.
from datetime import datetime
# Patches for the environment and for the HTTP post.
from unittest import mock

# The HTTP library under the RPC client: its post is replaced and its errors are the ones raised.
import requests

# The module under test.
from ratio1.bc import evm
# The name of the environment key that chooses the network.
from ratio1.const.base import dAuth


# The node address whose license is read.
NODE = "0x000000000000000000000000000000000000dEaD"
# Seconds one RPC request may take and tries one RPC call gets: a license read that the endpoint never answers
# ends after 2 tries of 10 s and the client's one pause of 0.125 s between them, about 20 s.
TIMEOUT, TRIES = 10, 2


class _Engine(evm._EVMMixin):
  """
  The EVM part of the block engine with the two things it takes from the full engine.

  Notes
  -----
  The full engine supplies the first-check flags and the logger. Here every first check counts as done and the
  logger only turns a network's genesis date into a datetime.
  """

  def __init__(self):
    """
    Give the EVM part its first-check flags and a logger stand-in.

    Returns
    -------
    None
    """
    # Every first check counts as done, so choosing the network prints nothing.
    self._first_checks_done = defaultdict(lambda: True)
    # The logger is asked for one thing on this path: the genesis date of the network as a datetime.
    self.log = mock.Mock()
    # Any date serves: a license read does not use it.
    self.log.str_to_date.return_value = datetime(2025, 5, 23, 16)

  def P(self, *args, **kwargs):
    """
    Drop a log line.

    Parameters
    ----------
    *args : tuple
      The message and positional options of the engine's log call.
    **kwargs : dict
      The keyword options of the engine's log call.

    Returns
    -------
    None
    """
    return


class _FakeEndpoint:
  """
  An RPC endpoint in memory, called in place of ``requests.Session.post``.

  It answers ``eth_chainId`` with a chain id and any other method with the 32-byte word for True, the answer of
  a license read for a licensed node. A method named in ``stalled`` gets no answer (a read timeout) and a method
  named in ``status`` gets that HTTP status with an empty body.

  Examples
  --------
  >>> endpoint = _FakeEndpoint()
  >>> endpoint.stalled.add("eth_call")  # license reads now time out
  """

  def __init__(self):
    """
    Start with no request seen and every method answered.

    Returns
    -------
    None
    """
    # (JSON-RPC method, timeout the client passed) of every request, in the order they came.
    self.seen = []
    # Methods that get no answer: the request ends in a read timeout.
    self.stalled = set()
    # Method -> HTTP status answered in place of a result.
    self.status = {}

  def post(self, url, data=None, **kwargs):
    """
    Record one request and answer it.

    Parameters
    ----------
    url : str
      The endpoint address the client posts to.
    data : bytes
      The JSON-RPC request body.
    **kwargs : dict
      The options the client passes to ``requests``; ``timeout`` is recorded.

    Returns
    -------
    requests.Response
      The JSON-RPC answer, or an empty answer with the HTTP status set for the method.

    Raises
    ------
    requests.ReadTimeout
      When the method is in ``stalled``.

    Examples
    --------
    >>> _FakeEndpoint().post("https://rpc.example", b'{"method": "eth_chainId", "id": 1}', timeout=10).json()
    {'jsonrpc': '2.0', 'id': 1, 'result': '0x2105'}
    """
    # The request as the client encoded it.
    request = json.loads(data)
    # Its method, with the timeout the client asked ``requests`` to apply.
    self.seen.append((request["method"], kwargs["timeout"]))
    if request["method"] in self.stalled:
      # No answer within the timeout: what ``requests`` raises for it.
      raise requests.ReadTimeout("no answer")
    # The response object the client gets back.
    response = requests.Response()
    # Its body is complete: nothing is left to read from a connection when the client closes it.
    response._content_consumed = True
    # The status set for this method, 200 for the others.
    response.status_code = self.status.get(request["method"], 200)
    # The chain id (Base) for eth_chainId; for every other method the 32-byte word for True.
    result = "0x2105" if request["method"] == "eth_chainId" else "0x" + "1".rjust(64, "0")
    # The JSON-RPC answer under the id of the request; no body when the status is an error.
    response._content = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode() \
      if response.status_code == 200 else b""
    # Handed to the client as the answer of its post.
    return response

  def calls(self, method):
    """
    Timeouts of the requests seen for one method.

    Parameters
    ----------
    method : str
      The JSON-RPC method to pick.

    Returns
    -------
    list
      The timeout of each request for that method, in order; its length is the number of tries.

    Examples
    --------
    >>> endpoint.calls("eth_call")  # after one license read that was tried twice
    [10, 10]
    """
    # One entry per request of that method.
    return [timeout for seen, timeout in self.seen if seen == method]


class RpcBoundsTests(unittest.TestCase):
  """The license read with the engine's own RPC client and with the client made for a named network."""

  def setUp(self):
    """Use devnet as the engine's network and route every HTTP post of the RPC client to the fake endpoint."""
    # The engine's network: its RPC client is built for it on first use.
    env = mock.patch.dict(os.environ, {dAuth.DAUTH_NET_ENV_KEY: "devnet"})
    # In force for the length of one test.
    env.start()
    # The environment is restored after the test.
    self.addCleanup(env.stop)
    # The endpoint every request of this test reaches.
    self.endpoint = _FakeEndpoint()
    # The RPC client posts through a requests session: the post is the only step replaced.
    post = mock.patch.object(requests.Session, "post", side_effect=self.endpoint.post)
    # In force for the length of one test.
    post.start()
    # The real post is restored after the test.
    self.addCleanup(post.stop)
    # The EVM part of the engine under test.
    self.engine = _Engine()

  def test_every_request_of_a_license_read_carries_the_timeout(self):
    """Each HTTP request a license read makes, the chain id fetch included, is given the 10 s timeout."""
    # A licensed node: the read answers True.
    self.assertTrue(self.engine.web3_is_node_licensed(NODE))
    # Both kinds of request were made.
    self.assertEqual({method for method, _ in self.endpoint.seen}, {"eth_chainId", "eth_call"})
    # None was left to the client library's own default of 30 s.
    self.assertEqual({timeout for _, timeout in self.endpoint.seen}, {TIMEOUT})

  def test_chain_id_is_fetched_for_the_first_read_only(self):
    """Three license reads on one thread: the chain id is fetched before the first, then each read is one request."""
    # Three reads in a row, all for a licensed node.
    self.assertEqual([self.engine.web3_is_node_licensed(NODE) for _ in range(3)], [True] * 3)
    # The methods in the order the endpoint saw them.
    methods = [method for method, _ in self.endpoint.seen]
    # Where the first license read itself starts.
    first = methods.index("eth_call")
    # The chain id was asked for before it.
    self.assertIn("eth_chainId", methods[:first])
    # From then on there are three license reads and nothing else: before, each read fetched the chain id twice.
    self.assertEqual(methods[first:], ["eth_call"] * 3)
    # The chain id is the only answer the client is told it may keep.
    self.assertEqual(self.engine.web3.provider.cacheable_requests, {"eth_chainId"})

  def test_an_unanswered_or_refused_license_read_ends_after_two_tries(self):
    """A read the endpoint never answers, or answers with HTTP 429, is tried twice, raises, and is not remembered."""
    # A first read, so the chain id is already known and only the license read itself is counted below.
    self.assertTrue(self.engine.web3_is_node_licensed(NODE))
    # No answer first, then the endpoint's "too many requests".
    for name, error in (("no answer", requests.Timeout), ("HTTP 429", requests.HTTPError)):
      # Each case reports on its own.
      with self.subTest(case=name):
        # Forget the requests seen so far.
        del self.endpoint.seen[:]
        # The license read gets no answer in the first case only.
        self.endpoint.stalled = {"eth_call"} if error is requests.Timeout else set()
        # It gets HTTP 429 in the second case only.
        self.endpoint.status = {} if error is requests.Timeout else {"eth_call": 429}
        # The caller gets the error itself: no verdict is made up.
        with self.assertRaises(error):
          # The read that fails.
          self.engine.web3_is_node_licensed(NODE)
        # Two tries, each with the timeout, and no other request: before, there were five tries of 30 s.
        self.assertEqual(self.endpoint.seen, [("eth_call", TIMEOUT)] * TRIES)
    # The endpoint answers again.
    self.endpoint.stalled, self.endpoint.status = set(), {}
    # The failures were not kept: the next read is asked anew and answers True.
    self.assertTrue(self.engine.web3_is_node_licensed(NODE))

  def test_an_unanswered_chain_id_fetch_ends_after_two_tries_and_is_asked_again(self):
    """The chain id fetch has the same bound: two tries, the error raised, no license read sent, nothing kept."""
    # The endpoint does not answer the chain id.
    self.endpoint.stalled = {"eth_chainId"}
    # The caller of the license read gets the timeout.
    with self.assertRaises(requests.Timeout):
      # The engine's first read, which needs the chain id.
      self.engine.web3_is_node_licensed(NODE)
    # Two tries for the chain id and no license read without it.
    self.assertEqual(self.endpoint.seen, [("eth_chainId", TIMEOUT)] * TRIES)
    # The endpoint answers again.
    self.endpoint.stalled = set()
    # The next read works.
    self.assertTrue(self.engine.web3_is_node_licensed(NODE))
    # The failed fetch was not kept: the chain id was asked for again, beyond the two failed tries.
    self.assertGreater(len(self.endpoint.calls("eth_chainId")), TRIES)

  def test_the_client_made_for_a_named_network_has_the_same_bounds(self):
    """A read for a network other than the engine's builds its own client: same timeout, same two tries."""
    # The license read gets no answer.
    self.endpoint.stalled = {"eth_call"}
    # The caller gets the timeout.
    with self.assertRaises(requests.Timeout):
      # testnet is not the engine's network, so a client is built for this one call.
      self.engine.web3_is_node_licensed(NODE, network="testnet")
    # Two tries of the license read, each with the timeout.
    self.assertEqual(self.endpoint.calls("eth_call"), [TIMEOUT] * TRIES)
    # The chain id fetch before them carried it too.
    self.assertEqual(set(self.endpoint.calls("eth_chainId")), {TIMEOUT})


# Run this file on its own.
if __name__ == '__main__':
  # The standard runner.
  unittest.main()
