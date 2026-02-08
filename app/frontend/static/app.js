const registerForm = document.getElementById("register-form");
const loginForm = document.getElementById("login-form");
const postForm = document.getElementById("post-form");
const refreshButton = document.getElementById("refresh-posts");
const tokenOutput = document.getElementById("token-output");
const postList = document.getElementById("post-list");
const logBox = document.getElementById("log");
const oauthProviders = document.getElementById("oauth-providers");

const tokenStoreKey = "fastapi_template_token";

function getToken() {
  return window.localStorage.getItem(tokenStoreKey) || "";
}

function setToken(token) {
  window.localStorage.setItem(tokenStoreKey, token);
  tokenOutput.value = token;
}

function clearAuthHash() {
  if (window.location.hash) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}

function log(message) {
  const stamp = new Date().toLocaleTimeString();
  logBox.textContent = `[${stamp}] ${message}\n${logBox.textContent}`.trim();
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      // Keep fallback detail if response is not JSON.
    }
    throw new Error(detail);
  }
  return response;
}

function renderPosts(posts) {
  postList.innerHTML = "";
  for (const item of posts) {
    const li = document.createElement("li");
    li.innerHTML = `
      <p class="post-title">${item.Post.title}</p>
      <p class="post-meta">Post #${item.Post.id} • Votes: ${item.votes}</p>
      <p class="post-content">${item.Post.content}</p>
    `;
    postList.appendChild(li);
  }
}

function renderOAuthProviders(providers) {
  oauthProviders.innerHTML = "";
  if (!providers.length) {
    oauthProviders.textContent = "No OAuth providers configured.";
    return;
  }

  for (const provider of providers) {
    const link = document.createElement("a");
    link.href = provider.start_url;
    link.className = "oauth-link";
    link.textContent = `Continue with ${provider.display_name}`;
    oauthProviders.appendChild(link);
  }
}

async function loadOAuthProviders() {
  try {
    const response = await fetch("/api/v1/auth/oauth/providers");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    renderOAuthProviders(payload.providers || []);
  } catch (error) {
    oauthProviders.textContent = "Could not load OAuth providers.";
    log(`OAuth provider list failed: ${error.message}`);
  }
}

async function handleOAuthCallbackHash() {
  if (!window.location.hash) {
    return;
  }

  const params = new URLSearchParams(window.location.hash.slice(1));
  const oauthError = params.get("error");
  const provider = params.get("provider") || "provider";
  const accessToken = params.get("access_token");

  if (oauthError) {
    log(`OAuth login failed (${provider}): ${oauthError}`);
    clearAuthHash();
    return;
  }

  if (!accessToken) {
    return;
  }

  setToken(accessToken);
  log(`Logged in with ${provider}.`);
  clearAuthHash();
  await loadPosts();
}

async function loadPosts() {
  try {
    const response = await apiFetch("/api/v1/posts/");
    const posts = await response.json();
    renderPosts(posts);
    log(`Loaded ${posts.length} posts.`);
  } catch (error) {
    log(`Could not load posts: ${error.message}`);
  }
}

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.getElementById("register-email").value;
  const password = document.getElementById("register-password").value;
  try {
    await apiFetch("/api/v1/users/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    log(`User created: ${email}`);
    registerForm.reset();
  } catch (error) {
    log(`User creation failed: ${error.message}`);
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  const body = new URLSearchParams({
    username: email,
    password,
  });

  try {
    const response = await fetch("/api/v1/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    const payload = await response.json();
    setToken(payload.access_token);
    log(`Logged in as ${email}`);
    await loadPosts();
  } catch (error) {
    log(`Login failed: ${error.message}`);
  }
});

postForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = document.getElementById("post-title").value;
  const content = document.getElementById("post-content").value;

  try {
    await apiFetch("/api/v1/posts/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, content }),
    });
    postForm.reset();
    log("Post created.");
    await loadPosts();
  } catch (error) {
    log(`Could not create post: ${error.message}`);
  }
});

refreshButton.addEventListener("click", loadPosts);

setToken(getToken());
loadOAuthProviders();
handleOAuthCallbackHash().then(() => {
  if (getToken()) {
    loadPosts();
  }
});
