const crypto = require("node:crypto");
const { inflateRawSync } = require("node:zlib");

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

  if (run.status !== "completed") {
    return jsonResponse(200, result);
  }

  const jobsUrl = `https://api.github.com/repos/${repository}/actions/runs/${run.id}/jobs?per_page=100`;
  const jobsResponse = await fetch(jobsUrl, { headers: githubHeaders(token) });
  if (!jobsResponse.ok) {
    console.error(`GitHub failed-job lookup failed with status ${jobsResponse.status}.`);
    if (run.conclusion === "success") {
      result.site_url_error = "Workflow succeeded, but its job logs could not be retrieved to find the live-site URL.";
    }
    return jsonResponse(200, result);
  }

  const jobsPayload = await jobsResponse.json();
  if (!Array.isArray(jobsPayload.jobs)) {
    console.error("GitHub workflow jobs response did not contain a jobs list.");
    if (run.conclusion === "success") {
      result.site_url_error = "Workflow succeeded, but GitHub returned an invalid job list.";
    }
    return jsonResponse(200, result);
  }

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

  if (run.conclusion === "success") {
    for (const job of jobsPayload.jobs) {
      try {
        const siteUrl = await getSiteUrlFromJobLogs(repository, token, job.id);
        if (siteUrl) {
          result.site_url = siteUrl;
          delete result.site_url_error;
          break;
        }
      } catch (error) {
        console.error(`Could not extract the deployed site URL from job ${job.id}:`, error);
        result.site_url_error = "Workflow succeeded, but the live-site URL could not be read from the workflow logs.";
      }
    }
    if (!result.site_url && !result.site_url_error) {
      result.site_url_error = "No live-site URL was found in the workflow logs; deployment may have been disabled.";
    }
  }

  return jsonResponse(200, result);
}

async function getSiteUrlFromJobLogs(repository, token, jobId) {
  const logsUrl = `https://api.github.com/repos/${repository}/actions/jobs/${jobId}/logs`;
  const response = await fetch(logsUrl, { headers: githubHeaders(token) });
  if (!response.ok) {
    throw new Error(`GitHub returned HTTP ${response.status} for job logs.`);
  }

  const archive = Buffer.from(await response.arrayBuffer());
  const endOfCentralDirectory = archive.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (endOfCentralDirectory < 0) {
    throw new Error("GitHub job log response was not a ZIP archive.");
  }

  const entryCount = archive.readUInt16LE(endOfCentralDirectory + 10);
  let centralDirectoryOffset = archive.readUInt32LE(endOfCentralDirectory + 16);
  const siteUrlPattern = /\[DEPLOY SUCCESS\] Site is LIVE at:\s*(https:\/\/[^\s]+)/;

  for (let entryIndex = 0; entryIndex < entryCount; entryIndex += 1) {
    if (archive.readUInt32LE(centralDirectoryOffset) !== 0x02014b50) {
      throw new Error("GitHub job log ZIP archive has an invalid directory entry.");
    }

    const compressionMethod = archive.readUInt16LE(centralDirectoryOffset + 10);
    const compressedSize = archive.readUInt32LE(centralDirectoryOffset + 20);
    const filenameLength = archive.readUInt16LE(centralDirectoryOffset + 28);
    const extraLength = archive.readUInt16LE(centralDirectoryOffset + 30);
    const commentLength = archive.readUInt16LE(centralDirectoryOffset + 32);
    const localHeaderOffset = archive.readUInt32LE(centralDirectoryOffset + 42);
    const filename = archive.toString(
      "utf8",
      centralDirectoryOffset + 46,
      centralDirectoryOffset + 46 + filenameLength,
    );

    if (archive.readUInt32LE(localHeaderOffset) !== 0x04034b50) {
      throw new Error(`GitHub job log ZIP entry "${filename}" is invalid.`);
    }

    const localFilenameLength = archive.readUInt16LE(localHeaderOffset + 26);
    const localExtraLength = archive.readUInt16LE(localHeaderOffset + 28);
    const dataOffset = localHeaderOffset + 30 + localFilenameLength + localExtraLength;
    const compressedData = archive.subarray(dataOffset, dataOffset + compressedSize);
    let logData;

    if (compressionMethod === 0) {
      logData = compressedData.toString("utf8");
    } else if (compressionMethod === 8) {
      logData = inflateRawSync(compressedData).toString("utf8");
    } else {
      throw new Error(`GitHub job log ZIP uses unsupported compression method ${compressionMethod}.`);
    }

    const match = logData.match(siteUrlPattern);
    if (match) {
      const siteUrl = new URL(match[1]);
      if (siteUrl.protocol === "https:") return siteUrl.toString();
    }

    centralDirectoryOffset += 46 + filenameLength + extraLength + commentLength;
  }

  return null;
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
