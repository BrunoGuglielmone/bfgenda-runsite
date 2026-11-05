const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
};

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: JSON_HEADERS,
  });
}

export default {
  async fetch(request) {
    if (request.method !== "POST") {
      return json({ detail: "Method not allowed." }, 405);
    }

    if (!request.headers.get("x-neon-trigger-invocation-id")) {
      return json({ detail: "Forbidden." }, 403);
    }

    const endpoint = process.env.RENDER_DISPATCH_URL;
    const token = process.env.RENDER_DISPATCH_TOKEN;

    if (!endpoint || !token) {
      return json({ detail: "Scheduler is not configured." }, 503);
    }

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          authorization: `Bearer ${token}`,
          "user-agent": "BFGenda-Neon-Scheduler/1.0",
        },
        signal: AbortSignal.timeout(55_000),
      });

      return json(
        { ok: response.ok, status: response.status },
        response.ok ? 200 : 502,
      );
    } catch (error) {
      return json(
        {
          ok: false,
          detail: error instanceof Error ? error.name : "FetchError",
        },
        502,
      );
    }
  },
};
