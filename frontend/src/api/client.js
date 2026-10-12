
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export async function apiRequest(path, options = {}) {
  const headers = { ...options.headers };

  // Set the correct content type based on the request body.
  if (options.body instanceof FormData) {
    // Browser sets multipart/form-data boundary automatically.
  } else if (options.body instanceof URLSearchParams) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  // Attach JWT to protected requests.
  const token = localStorage.getItem("access_token");

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type");

  const data = contentType?.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    let message = "Something went wrong";

    if (typeof data === "string") {
      message = data || message;
    } else if (Array.isArray(data.detail)) {
      message = data.detail
        .map((item) => {
          const field = item.loc?.slice(1).join(".");
          const description = item.msg || "Invalid value";

          return field
            ? `${field}: ${description}`
            : description;
        })
        .join("; ");
    } else if (typeof data.detail === "string") {
      message = data.detail;
    }

    throw new Error(message);
  }

  return data;
}
