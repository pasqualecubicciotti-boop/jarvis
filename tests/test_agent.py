import anthropic
import httpx

from conftest import make_message, text, tool_use


async def test_plain_answer_uses_cheap_defaults(make_agent):
    agent, client = make_agent([make_message(text("Ciao!"))])
    reply = await agent.handle_message(1, "ciao")
    assert reply.text == "Ciao!" and not reply.needs_confirmation
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] == 1024
    assert call["output_config"] == {"effort": "low"}


async def test_tool_loop_saves_reminder(make_agent):
    agent, client = make_agent([
        make_message(tool_use("save_reminder", {"text": "latte"}), stop_reason="tool_use"),
        make_message(text("Fatto.")),
    ])
    reply = await agent.handle_message(1, "ricordami il latte")
    assert reply.text == "Fatto."
    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and "salvato" in result["content"]


async def test_confirmation_yes_executes(make_agent, sent):
    agent, _ = make_agent([
        make_message(tool_use("send_email", {"to": "a@b.it"}), stop_reason="tool_use"),
        make_message(text("Inviata.")),
    ])
    reply = await agent.handle_message(1, "scrivi ad a@b.it")
    assert reply.needs_confirmation and "a@b.it" in reply.text
    assert sent == []  # NON ancora eseguito
    reply = await agent.resolve_confirmation(1, True)
    assert sent == ["a@b.it"] and reply.text == "Inviata."


async def test_confirmation_no_blocks_action(make_agent, sent):
    agent, client = make_agent([
        make_message(tool_use("send_email", {"to": "a@b.it"}), stop_reason="tool_use"),
        make_message(text("Ok, annullato.")),
    ])
    await agent.handle_message(1, "scrivi")
    reply = await agent.resolve_confirmation(1, False)
    assert sent == [] and reply.text == "Ok, annullato."
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True


async def test_mixed_tools_keep_all_results(make_agent, sent):
    agent, client = make_agent([
        make_message(
            tool_use("get_datetime", {}, id="t1"),
            tool_use("send_email", {"to": "x@y.it"}, id="t2"),
            stop_reason="tool_use",
        ),
        make_message(text("ok")),
    ])
    await agent.handle_message(1, "x")
    await agent.resolve_confirmation(1, True)
    ids = [r["tool_use_id"] for r in client.calls[1]["messages"][-1]["content"]]
    assert ids == ["t1", "t2"]


async def test_new_message_while_pending_asks_again(make_agent, sent):
    agent, client = make_agent([make_message(tool_use("send_email", {"to": "a@b.it"}), stop_reason="tool_use")])
    await agent.handle_message(1, "scrivi")
    reply = await agent.handle_message(1, "boh")
    assert reply.needs_confirmation and sent == [] and len(client.calls) == 1


async def test_daily_limit_blocks_model(make_agent):
    agent, client = make_agent([make_message(text("r")) for _ in range(5)])
    for _ in range(5):
        await agent.handle_message(1, "q")
    reply = await agent.handle_message(1, "q")
    assert "limite" in reply.text and len(client.calls) == 5


async def test_api_error_is_logged_and_history_stays_valid(make_agent, usage):
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    agent, client = make_agent([err, make_message(text("ok"))])
    reply = await agent.handle_message(1, "uno")
    assert "problema" in reply.text and usage.today()["errors"] == 1
    await agent.handle_message(1, "due")
    assert client.calls[1]["messages"] == [{"role": "user", "content": "due"}]


async def test_unknown_tool_and_refusal(make_agent):
    agent, client = make_agent([
        make_message(tool_use("hack", {}), stop_reason="tool_use"),
        make_message(stop_reason="refusal"),
    ])
    reply = await agent.handle_message(1, "x")
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True
    assert "Non posso" in reply.text
