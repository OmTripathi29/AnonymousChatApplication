import json
import asyncio
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.redis_client import get_redis_client

@pytest.mark.asyncio
async def test_1v1_matching_skip_and_images(async_client):
    # 1. Authenticate Guest A and Guest B
    res_a = await async_client.post("/api/v1/auth/guest")
    assert res_a.status_code == 200
    user_a = res_a.json()

    res_b = await async_client.post("/api/v1/auth/guest")
    assert res_b.status_code == 200
    user_b = res_b.json()

    redis = await get_redis_client()

    with TestClient(app) as client:
        # 2. Connect Guest A
        with client.websocket_connect(f"/ws/match?token={user_a['token']}") as ws_a:
            # Guest A should receive a "searching" event since they are alone in queue
            msg_a1 = ws_a.receive_json()
            assert msg_a1["type"] == "searching"

            # Check they are in waitlist
            waitlist = await redis.smembers("matchmaker:waitlist")
            assert user_a["userId"] in waitlist

            # 3. Connect Guest B
            with client.websocket_connect(f"/ws/match?token={user_b['token']}") as ws_b:
                # Guest B joins, which triggers a match between A and B!
                # Both should receive "matched" events via their sockets
                msg_b1 = ws_b.receive_json()
                assert msg_b1["type"] == "matched"
                assert msg_b1["partnerName"] == user_a["username"]
                assert msg_b1["avatarHash"] == user_a["avatarHash"]

                # Guest A receives match notification published over Pub/Sub
                msg_a2 = ws_a.receive_json()
                assert msg_a2["type"] == "matched"
                assert msg_a2["partnerName"] == user_b["username"]
                assert msg_a2["avatarHash"] == user_b["avatarHash"]

                # Assert both are removed from the waitlist
                waitlist_after = await redis.smembers("matchmaker:waitlist")
                assert user_a["userId"] not in waitlist_after
                assert user_b["userId"] not in waitlist_after

                # 4. Exchange chat message and base64 image from A to B
                # Send text and a base64 mock image
                ws_a.send_json({
                    "type": "chat_message",
                    "message": "Hello partner!",
                    "image": "data:image/jpeg;base64,mockstring=="
                })

                # B receives message
                msg_b_chat = ws_b.receive_json()
                assert msg_b_chat["type"] == "chat_message"
                assert msg_b_chat["userId"] == user_a["userId"]
                assert msg_b_chat["message"] == "Hello partner!"
                assert msg_b_chat["image"] == "data:image/jpeg;base64,mockstring=="

                # 5. Skip chat: A skips B
                ws_a.send_json({
                    "type": "skip"
                })

                # A receives "skipped" confirmation
                msg_a_skip = ws_a.receive_json()
                assert msg_a_skip["type"] == "skipped"

                # B receives "partner_skipped" notification
                msg_b_skip = ws_b.receive_json()
                assert msg_b_skip["type"] == "partner_skipped"

                # 6. Verify Redis keys are cleaned up
                room_a = await redis.get(f"user:match:{user_a['userId']}")
                room_b = await redis.get(f"user:match:{user_b['userId']}")
                partner_a = await redis.get(f"user:partner:{user_a['userId']}")
                partner_b = await redis.get(f"user:partner:{user_b['userId']}")

                assert room_a is None
                assert room_b is None
                assert partner_a is None
                assert partner_b is None
