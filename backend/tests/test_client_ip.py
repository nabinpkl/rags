"""Tests for askrag.api.client_ip: which X-Forwarded-For entry is the visitor
(D11's per-IP cap is only per-IP if this is right)."""

import pytest

from askrag.api.client_ip import client_ip, parse_networks

COMPOSE = parse_networks(["10.120.0.0/24"])


def test_untrusted_peer_is_the_client_whatever_the_header_says():
    assert client_ip("203.0.113.9", "1.1.1.1", COMPOSE) == "203.0.113.9"


def test_no_header_falls_back_to_the_peer():
    assert client_ip("10.120.0.3", None, COMPOSE) == "10.120.0.3"


def test_behind_caddy_the_rightmost_untrusted_hop_is_the_visitor():
    # tailscale serve set the visitor, Caddy appended the docker gateway.
    assert client_ip("10.120.0.3", "100.71.2.3, 10.120.0.1", COMPOSE) == "100.71.2.3"


def test_a_client_seeded_entry_left_of_the_real_one_is_ignored():
    forged = "9.9.9.9, 100.71.2.3, 10.120.0.1"
    assert client_ip("10.120.0.3", forged, COMPOSE) == "100.71.2.3"


def test_two_visitors_behind_the_same_proxy_get_different_keys():
    a = client_ip("10.120.0.3", "100.71.2.3, 10.120.0.1", COMPOSE)
    b = client_ip("10.120.0.3", "100.80.4.5, 10.120.0.1", COMPOSE)
    assert a != b


def test_an_all_trusted_chain_resolves_to_its_origin():
    assert client_ip("10.120.0.3", "10.120.0.7, 10.120.0.1", COMPOSE) == "10.120.0.7"


def test_nothing_trusted_means_the_header_is_never_read():
    assert client_ip("10.120.0.3", "100.71.2.3", ()) == "10.120.0.3"


def test_missing_peer_is_unknown():
    assert client_ip(None, "100.71.2.3", COMPOSE) == "unknown"


def test_a_malformed_cidr_raises_rather_than_trusting_nothing():
    with pytest.raises(ValueError):
        parse_networks(["10.120.0.0/33"])
