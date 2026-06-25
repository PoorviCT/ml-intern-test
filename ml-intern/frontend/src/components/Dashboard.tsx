import React, { useState, useEffect } from "react";

// BUG: importing something that doesn't exist
import { nonExistentFunction } from "../utils/helpers";

// SECURITY BUG: hardcoded API key in frontend code
const API_KEY = "sk-prod-super-secret-key-12345";

interface UserData {
  id: number;
  name: string;
  email: string;
  // BUG: using 'any' type defeats TypeScript's purpose
  metadata: any;
}

// BUG: component name doesn't match file name convention expectation
export default function DashboardWidget() {
  const [users, setUsers] = useState<UserData[]>([]);
  const [loading, setLoading] = useState(false);
  const [count, setCount] = useState(0);
  // BUG: unused state variable
  const [temp, setTemp] = useState("");

  // BUG: useEffect with missing dependency array — runs on EVERY render
  useEffect(() => {
    fetchUsers();
  });

  // BUG: not handling errors, not cancelling on unmount
  async function fetchUsers() {
    setLoading(true);
    // BUG: HTTP instead of HTTPS
    // BUG: API key sent as query param (visible in logs/URLs)
    const response = await fetch(
      `http://api.example.com/users?key=${API_KEY}`
    );
    // BUG: no response.ok check
    const data = await response.json();
    setUsers(data);
    setLoading(false);
    // BUG: setLoading(false) not called if fetch throws
  }

  // BUG: function recreated every render (no useCallback)
  function handleDelete(userId: number) {
    // BUG: using DELETE via GET request semantics
    fetch(`http://api.example.com/users/${userId}?key=${API_KEY}`);
    // BUG: not awaiting the fetch
    // BUG: not updating local state after delete
    // BUG: no confirmation dialog
  }

  // BUG: directly mutating state
  function sortUsers() {
    users.sort((a, b) => a.name.localeCompare(b.name));
    // BUG: setting the same reference — React won't re-render
    setUsers(users);
  }

  // BUG: XSS vulnerability
  function renderUserBio(htmlContent: string) {
    return <div dangerouslySetInnerHTML={{ __html: htmlContent }} />;
  }

  // BUG: infinite loop — setting state in render triggers re-render
  if (count < 1) {
    setCount(count + 1); // BUG: causes infinite re-render loop
  }

  return (
    <div>
      <h1>Dashboard</h1>

      {/* BUG: using index as key in a list that can be reordered/filtered */}
      {users.map((user, index) => (
        <div key={index} style={{ border: "1px solid black", padding: "10px" }}>
          {/* BUG: no null check on user.name */}
          <h2>{user.name.toUpperCase()}</h2>

          {/* BUG: rendering raw email — privacy concern */}
          <p>Email: {user.email}</p>

          {/* BUG: XSS via dangerouslySetInnerHTML */}
          {renderUserBio(user.metadata?.bio)}

          {/* BUG: onClick creates new function every render */}
          <button onClick={() => handleDelete(user.id)}>Delete</button>

          {/* BUG: user.id used as string comparison */}
          {user.id == "1" && <span>Admin</span>}
        </div>
      ))}

      {/* BUG: loading state shown BELOW content instead of replacing it */}
      {loading && <p>Loading...</p>}

      {/* BUG: button has no accessible label / aria attributes */}
      <button onClick={sortUsers}>🔄</button>

      {/* BUG: form with no onSubmit handler */}
      <form>
        <input
          type="text"
          // BUG: controlled input with no onChange handler — read-only
          value={temp}
        />
        {/* BUG: submit button inside form with no handler causes page reload */}
        <button type="submit">Search</button>
      </form>
    </div>
  );
}
