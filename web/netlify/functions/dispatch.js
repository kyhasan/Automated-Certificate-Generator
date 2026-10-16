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

function githubHeaders(token) {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${token}`,
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
  };
}

async function getWorkflowStatus(repository, token, workflowRef, requestId) {
  const runsUrl = new URL(`https://api.github.com/repos/${repository}/actions/workflows/${workflowFile}/runs`);
  runsUrl.searchParams.set("branch", workflowRef);
  runsUrl.searchParams.set("event", "workflow_dispatch");
  runsUrl.searchParams.set("per_page", "100");

  const runsResponse = await fetch(runsUrl, { headers: githubHeaders(token) });
  if (!runsResponse.ok) {
    console.error(`GitHub workflow status lookup failed with status ${runsResponse.status}.`);
    return jsonResponse(502, { error: "Could not retrieve the GitHub workflow status." });
  }

  const runsPayload = await runsResponse.json();
  if (!Array.isArray(runsPayload.workflow_runs)) {
    console.error("GitHub workflow status response did not contain a workflow run list.");
    return jsonResponse(502, { error: "GitHub returned an invalid workflow status response." });
  }

  const run = runsPayload.workflow_runs.find(
    (workflowRun) => workflowRun.display_title === `Certificate generator ${requestId}`,
  );

  if (!run) {
    return jsonResponse(200, {
      status: "pending",
      message: "Workflow run is not visible yet. Checking again...",
    });
  }

  const result = {
    status: run.status,
    conclusion: run.conclusion,
    run_url: run.html_url,
    run_number: run.run_number,
    failure_details: [],
  };

  if (run.status !== "completed" || run.conclusion === "success") {
    return jsonResponse(200, result);
  }

  const jobsUrl = `https://api.github.com/repos/${repository}/actions/runs/${run.id}/jobs?per_page=100`;
  const jobsResponse = await fetch(jobsUrl, { headers: githubHeaders(token) });
  if (!jobsResponse.ok) {
    console.error(`GitHub failed-job lookup failed with status ${jobsResponse.status}.`);
    return jsonResponse(200, result);
  }

  const jobsPayload = await jobsResponse.json();
  result.failure_details = jobsPayload.jobs
    .filter((job) => job.conclusion && job.conclusion !== "success")
    .map((job) => {
      const failedSteps = (Array.isArray(job.steps) ? job.steps : [])
        .filter((step) => step.conclusion && step.conclusion !== "success")
        .map((step) => step.name);
      return failedSteps.length > 0
        ? `${job.name}: ${failedSteps.join(", ")}`
        : `${job.name}: ${job.conclusion}`;
    });

  return jsonResponse(200, result);
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

  if (payload.action === "status") {
    if (typeof payload.request_id !== "string" ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(payload.request_id)) {
      return jsonResponse(400, { error: "A valid workflow request ID is required." });
    }

    try {
      return await getWorkflowStatus(repository, token, workflowRef, payload.request_id);
    } catch (error) {
      console.error("GitHub workflow status request failed:", error);
      return jsonResponse(502, { error: "Could not connect to GitHub to retrieve workflow status." });
    }
  }

  if (payload.action !== "dispatch") {
    return jsonResponse(400, { error: "Unsupported cloud dispatch action." });
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
  const requestId = crypto.randomUUID();
  let githubResponse;
  try {
    githubResponse = await fetch(githubUrl, {
      method: "POST",
      headers: githubHeaders(token),
      body: JSON.stringify({
        ref: workflowRef,
        inputs: {
          tournament_url: tournamentUrl.toString(),
          category: payload.category || "",
          rounds: payload.rounds ? String(payload.rounds) : "",
          site_name: payload.site_name || "",
          deploy: String(payload.deploy),
          request_id: requestId,
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
    request_id: requestId,
  });
};
