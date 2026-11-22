# Apartment Luna – Guest Plugin

The plugin answers questions using excerpts from the Apartment Luna guest
guide. When a guest asks to open the door, ChatGPT displays the door card.
On first use, the guest links their valid access code on the FlatManager site.
They can then open the door using the button on the card. The QR code and
browser guest page still provide access without ChatGPT.

## Staging and deployment

The MCP adapter runs in the existing FastAPI application. For staging, use a
separate database, a test access code, and a test device.

1. Set the values from `api/.env.example` in `api/.env`.
   `CHATGPT_GUEST_PUBLIC_URL` is the HTTPS origin without a trailing slash.
   This setting enables the guest integration and requires a non-default
   `SECURITY_PEPPER`. `CHATGPT_GUEST_APARTMENT_ID` must match the apartment ID
   in FlatManager. Keep the existing pepper when using an existing database.
2. Proxy `/api/guest/chatgpt/` to FastAPI as you do for the rest of the guest
   API. Add these two exact Nginx locations to the server block for the same
   HTTPS origin. Keep the other client and device routes separate.

   ```nginx
   location = /.well-known/oauth-protected-resource/api/guest/chatgpt/mcp {
       proxy_pass http://127.0.0.1:8000;
   }
   location = /.well-known/oauth-authorization-server/api/guest/chatgpt {
       proxy_pass http://127.0.0.1:8000;
   }
   ```

   Configure the forwarding headers and trusted proxy as for the existing
   guest API. When guests link an access code, FlatManager uses the client IP
   to enforce its rate limits.
3. In the ChatGPT web client, connect the remote MCP endpoint
   `/api/guest/chatgpt/mcp` using **Plugins → Add custom MCP server**. Select
   mixed authentication with CIMD and check that the connection's exact
   client ID and callback URL match the FlatManager settings. `mcp.json`
   contains the planned production origin. To test the package against
   staging, change the URL in your test package.
4. Start with a question about checkout or quiet hours. Then open the door
   card, link the test code, and check the button, the device acknowledgment,
   repeat attempts, expired authorization, and revoked access. Test the full
   flow with a guest account on the target devices before public submission.

The authorization is tied to the existing access code and its apartment.
It expires no later than the original code's expiration time. FlatManager
checks for code changes and revocation on every request. On success, the
button shows the door opener's acknowledgment. The system does not measure
the physical position of the door.

The FAQ is in `api/src/flatmanager_api/routes/chatgpt_guest.py`. Update it when
the guest guide changes. Run `cd api && uv run pytest` to verify code
validation and door access.
