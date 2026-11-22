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
   Set `CHATGPT_GUEST_PUBLIC_URL=https://www.apartment-luna.cz` for the OAuth
   issuer, guest sign-in, and browser fallback. Set
   `CHATGPT_GUEST_MCP_URL=https://mcp.apartment-luna.cz` for the MCP origin.
   Omit trailing slashes. If the MCP origin is unset, it defaults to the public
   origin. Enabling the guest integration requires a non-default
   `SECURITY_PEPPER`. Keep the existing pepper when using an existing database.
   `CHATGPT_GUEST_APARTMENT_ID` must match the apartment ID in FlatManager.
2. Route `/api/guest/chatgpt/authorize` and `/api/guest/chatgpt/token` to
   FastAPI through the public guest API. On the MCP host, expose the OAuth
   protected-resource metadata.

   ```nginx
   location = /.well-known/oauth-protected-resource/api/guest/chatgpt/mcp {
       proxy_pass http://127.0.0.1:8000;
   }
   ```

   On the public OAuth host, expose the authorization server metadata.

   ```nginx
   location = /.well-known/oauth-authorization-server/api/guest/chatgpt {
       proxy_pass http://127.0.0.1:8000;
   }
   ```

   Keep the MCP route blocked on the other public hosts. On the dedicated
   host, configure Nginx to verify the OpenAI certificate chain and require
   `$ssl_client_verify` to be `SUCCESS` for `/api/guest/chatgpt/mcp`. Keep the
   protected-resource metadata publicly accessible.

   Set `CHATGPT_GUEST_MTLS_INTERMEDIATE` to the path to the official OpenAI
   Connectors intermediate certificate as seen by the API process. With the
   default Docker volume, `./api/data/openai-connectors-mtls-ca.pem` on the
   host is `/app/data/openai-connectors-mtls-ca.pem` in the container.
   Generate a dedicated random proxy token and set the same value in
   `CHATGPT_GUEST_MTLS_PROXY_TOKEN` and in a private Nginx configuration file.
   In the certificate-protected MCP location, set the following upstream
   headers so Nginx overwrites any client-supplied values:

   ```nginx
   proxy_set_header X-FlatManager-MTLS-Client-Cert $ssl_client_escaped_cert;
   proxy_set_header X-FlatManager-MTLS-Proxy-Token "<private proxy token>";
   ```

   Keep the API listener private and the proxy token out of logs and version
   control. Rotate the token independently of guest access codes.

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
