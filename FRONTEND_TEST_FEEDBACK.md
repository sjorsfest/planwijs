# Test Feedback — Frontend Integration Guide

A self-contained Canny-like feedback board for beta testers. All endpoints require authentication (`Authorization: Bearer <token>`).

---

## API Endpoints

Base URL: `/test-feedback`

### Feedback

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/test-feedback/` | List all feedback (newest first) |
| `POST` | `/test-feedback/` | Create new feedback |
| `GET` | `/test-feedback/{id}` | Get single feedback item |
| `DELETE` | `/test-feedback/{id}` | Delete own feedback |

### Votes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/test-feedback/{id}/vote` | Toggle upvote (idempotent toggle) |

### Comments

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/test-feedback/{id}/comments` | List comments on feedback |
| `POST` | `/test-feedback/{id}/comments` | Add a comment |
| `DELETE` | `/test-feedback/comments/{comment_id}` | Delete own comment |

---

## Request / Response Shapes

### Create Feedback

```json
// POST /test-feedback/
{
  "route": "/lesplan/overview",         // the page/route where the issue was found
  "name": "Login button not clear",     // short title
  "description": "I tried clicking...", // detailed description
  "type": "BUG"                         // "BUG" | "SUGGESTION" | "OTHER"
}
```

### Feedback Response

Every feedback item returns:

```json
{
  "id": "clx...",
  "user_id": "clx...",
  "user_name": "Jeroen",
  "route": "/lesplan/overview",
  "name": "Login button not clear",
  "description": "I tried clicking on a different element...",
  "type": "BUG",
  "vote_count": 3,
  "has_voted": true,          // whether the current user has upvoted
  "comment_count": 2,
  "created_at": "2026-04-16T12:00:00"
}
```

### Toggle Vote

```json
// POST /test-feedback/{id}/vote
// No request body needed

// Response:
{
  "voted": true,      // true = just voted, false = just unvoted
  "vote_count": 4
}
```

### Create Comment

```json
// POST /test-feedback/{id}/comments
{
  "text": "I have the same issue on Safari"
}
```

### Comment Response

```json
{
  "id": "clx...",
  "user_id": "clx...",
  "user_name": "Jeroen",
  "text": "I have the same issue on Safari",
  "created_at": "2026-04-16T12:05:00"
}
```

---

## Frontend Architecture

Keep this feature **completely isolated** from the rest of the app. Suggested structure:

```
src/
  features/
    test-feedback/
      api.ts              ← API client functions
      TestFeedbackPage.tsx ← Main page (the board)
      FeedbackCard.tsx     ← Single feedback card
      FeedbackDetail.tsx   ← Expanded view with comments
      NewFeedbackModal.tsx ← Create feedback form
      types.ts             ← TypeScript interfaces
```

### types.ts

```ts
export type FeedbackType = "BUG" | "SUGGESTION" | "OTHER";

export interface Feedback {
  id: string;
  user_id: string;
  user_name: string;
  route: string;
  name: string;
  description: string;
  type: FeedbackType;
  vote_count: number;
  has_voted: boolean;
  comment_count: number;
  created_at: string;
}

export interface Comment {
  id: string;
  user_id: string;
  user_name: string;
  text: string;
  created_at: string;
}

export interface VoteResponse {
  voted: boolean;
  vote_count: number;
}
```

---

## UI Layout Recommendation

### 1. Main Board (`/feedback`)

```
┌─────────────────────────────────────────────────┐
│  🧪 Feedback Board              [+ New Feedback]│
│─────────────────────────────────────────────────│
│  Filter: [All] [Bug] [Suggestion] [Other]       │
│  Sort:   [Most Voted] [Newest]                  │
│─────────────────────────────────────────────────│
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │ ▲  3  │ Login button not clear     BUG  │    │
│  │       │ /lesplan/overview               │    │
│  │       │ Jeroen · 2h ago · 4 comments    │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │ ▲  1  │ Add dark mode          SUGGEST  │    │
│  │       │ /settings                       │    │
│  │       │ Lisa · 1d ago · 0 comments      │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
└─────────────────────────────────────────────────┘
```

- **Left column**: upvote button + count. Highlighted if `has_voted` is true.
- **Right section**: title, type badge, route path, author + time + comment count.
- **Clicking a card** opens the detail view.
- **Filter chips**: filter by `type` (client-side filtering is fine).
- **Sort**: by `vote_count` desc or `created_at` desc (client-side).

### 2. Detail View (`/feedback/{id}`)

```
┌─────────────────────────────────────────────────┐
│  ← Back                                         │
│─────────────────────────────────────────────────│
│  Login button not clear                    BUG  │
│  Route: /lesplan/overview                       │
│  By Jeroen · April 16, 2026                     │
│                                                  │
│  I tried clicking on a different element all    │
│  the time, but it apparently was not the login  │
│  button.                                         │
│                                                  │
│  [▲ Upvote (3)]                                 │
│─────────────────────────────────────────────────│
│  Comments (2)                                    │
│                                                  │
│  Lisa · 1h ago                                  │
│  I have the same issue on Safari                │
│                                                  │
│  Jeroen · 30m ago                               │
│  Seems to be a z-index issue with the modal     │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │ Write a comment...              [Send]  │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### 3. New Feedback Modal

```
┌─────────────────────────────────────────────────┐
│  New Feedback                              [×]  │
│─────────────────────────────────────────────────│
│                                                  │
│  Type:  (●) Bug  ( ) Suggestion  ( ) Other      │
│                                                  │
│  Route: [ auto-filled with current path     ]   │
│                                                  │
│  Title: [ Short description of the issue    ]   │
│                                                  │
│  Description:                                    │
│  ┌─────────────────────────────────────────┐    │
│  │                                         │    │
│  │                                         │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│                              [Cancel] [Submit]  │
└─────────────────────────────────────────────────┘
```

**Key UX detail**: auto-fill the `route` field with the current page path (e.g. `window.location.pathname`) so the user doesn't have to type it.

---

## Implementation Tips

1. **Routing**: Add a single route `/feedback` (or `/test-feedback`) to your app router. This entire feature lives on that one page + its sub-views.

2. **Floating action button (optional)**: Consider a small floating "Give Feedback" button visible on every page that opens the New Feedback Modal with the current route pre-filled. This makes it super easy for testers to report issues in-context.

3. **Optimistic updates**: When toggling a vote, immediately update `vote_count` and `has_voted` in local state, then fire the API call. Revert on error.

4. **No coupling**: This feature should NOT import anything from other feature folders. It only needs the auth token (which you already have globally) and the API base URL.

5. **Removal**: When beta testing is done, you can remove the entire `features/test-feedback/` folder, the route, and the floating button. On the backend, drop the migration or keep the data for reference.
