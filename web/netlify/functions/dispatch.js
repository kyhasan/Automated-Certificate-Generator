const crypto = require("node:crypto");

const workflowFile = "generate_and_deploy.yml";

function jsonResponse(statusCode, payload) {
  return {
    statusCode,
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  };
}

function isOptionalString(value, maxLength) {
  return value === undefined || value === null ||
    (typeof value === "string" && value.length <= maxLength);
}

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return jsonResponse(405, { error: "Method not allowed." });
  }

  const expectedAccessKey = process.env.CERT_GENERATOR_UI_ACCESS_KEY;
  const providedAuthorization = event.headers.authorization || event.headers.Authorization || "";
  const providedAccessKey = providedAuthorization.startsWith("Bearer ")
    ? providedAuthorization.slice(7)
    : "";

  if (!expectedAccessKey) {
    console.error("Missing CERT_GENERATOR_UI_ACCESS_KEY environment variable.");
    return jsonResponse(500, { error: "Cloud dispatch is not configured." });
  }

  const expectedBuffer = Buffer.from(expectedAccessKey);
  const providedBuffer = Buffer.from(providedAccessKey);
  if (
    expectedBuffer.length !== providedBuffer.length ||
    !crypto.timingSafeEqual(expectedBuffer, providedBuffer)
  ) {
    return jsonResponse(401, { error: "Invalid dashboard access key." });
  }

  const repository = process.env.CERT_GENERATOR_GITHUB_REPOSITORY;
  const token = process.env.CERT_GENERATOR_GITHUB_TOKEN;
  const workflowRef = process.env.CERT_GENERATOR_WORKFLOW_REF;

  if (!repository || !token || !workflowRef) {
    console.error("Missing GitHub workflow configuration environment variables.");
    return jsonResponse(500, { error: "Cloud dispatch is not configured." });
  }

  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
    console.error("CERT_GENERATOR_GITHUB_REPOSITORY must be in owner/repo format.");
    return jsonResponse(500, { error: "Cloud dispatch repository configuration is invalid." });
  }

  let payload;
  try {
    payload = JSON.parse(event.body || "");
  } catch {
    return jsonResponse(400, { error: "Request body must be valid JSON." });
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return jsonResponse(400, { error: "Request body must be a JSON object." });
  }

  let tournamentUrl;
  try {
    tournamentUrl = new URL(payload.url);
  } catch {
    return jsonResponse(400, { error: "Enter a valid Chess-Results tournament URL." });
  }

  if (
    tournamentUrl.protocol !== "https:" ||
    (tournamentUrl.hostname !== "chess-results.com" &&
      !tournamentUrl.hostname.endsWith(".chess-results.com"))
  ) {
    return jsonResponse(400, { error: "Tournament URL must be on chess-results.com." });
  }

  if (
    !isOptionalString(payload.category, 100) ||
    !isOptionalString(payload.site_name, 100) ||
    (payload.rounds !== undefined && payload.rounds !== null &&
      (!Number.isInteger(payload.rounds) || payload.rounds < 1 || payload.rounds > 20)) ||
    typeof payload.deploy !== "boolean"
  ) {
    return jsonResponse(400, { error: "One or more request fields are invalid." });
  }

  const githubUrl = `https://api.github.com/repos/${repository}/actions/workflows/${workflowFile}/dispatches`;
  let githubResponse;
  try {
    githubResponse = await fetch(githubUrl, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: workflowRef,
        inputs: {
          tournament_url: tournamentUrl.toString(),
          category: payload.category || "",
          rounds: payload.rounds ? String(payload.rounds) : "",
          site_name: payload.site_name || "",
          deploy: String(payload.deploy),
        },
      }),
    });
  } catch (error) {
    console.error("GitHub workflow dispatch request failed:", error);
    return jsonResponse(502, { error: "Could not connect to GitHub to dispatch the workflow." });
  }

  if (!githubResponse.ok) {
    const responseText = (await githubResponse.text()).slice(0, 1000);
    console.error(`GitHub workflow dispatch failed with status ${githubResponse.status}: ${responseText}`);
    return jsonResponse(githubResponse.status, {
      error: `GitHub rejected the workflow dispatch (HTTP ${githubResponse.status}). Check the GitHub token permissions, workflow file, and branch.`,
    });
  }

  return jsonResponse(202, {
    actions_url: `https://github.com/${repository}/actions`,
  });
};
