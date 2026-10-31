# 🎬 CineCloud — Movie Ticket Booking App

A full-stack, production-ready movie ticket booking platform built with **React Native (Expo)** and **AWS Serverless Architecture**. Similar to BookMyShow.

---

## 📁 Project Structure

```
cinecloud/
├── frontend/                         # React Native (Expo) app
│   ├── app.json                      # Expo config
│   ├── babel.config.js               # Module aliases (@screens, @hooks, etc.)
│   ├── tsconfig.json
│   └── src/
│       ├── app/                      # Expo Router file-based navigation
│       │   ├── _layout.tsx           # Root layout (Redux + Amplify setup)
│       │   ├── (auth)/               # Auth screens (login, signup, otp)
│       │   ├── (tabs)/               # Main tab navigator
│       │   ├── movie/[id].tsx        # Movie details
│       │   ├── theatre/[movieId].tsx # Theatre & show selection
│       │   ├── seats/[showId].tsx    # Seat selection
│       │   ├── payment/[showId].tsx  # Payment + BNPL
│       │   └── ticket/[bookingId].tsx# Booking confirmation + QR
│       ├── components/
│       │   ├── common/               # Button, Input, Header, Badge, etc.
│       │   ├── seat/                 # SeatMap, SeatLegend, GenderIndicator
│       │   ├── payment/              # PaymentOptions, BNPLCard
│       │   └── chatbot/              # ChatBubble, QuickReplies
│       ├── store/
│       │   ├── index.ts              # Redux store + persist config
│       │   └── slices/
│       │       ├── authSlice.ts      # User auth state
│       │       ├── moviesSlice.ts    # Movies list + search
│       │       ├── bookingSlice.ts   # Active booking flow
│       │       ├── bnplSlice.ts      # BNPL credit state
│       │       └── chatSlice.ts      # Chatbot messages
│       ├── services/
│       │   ├── api.ts                # Axios wrapper (auto JWT injection)
│       │   └── websocket.ts          # Real-time seat updates
│       ├── constants/
│       │   ├── theme.ts              # Colors, typography, spacing, seat config
│       │   └── awsConfig.ts          # Amplify + Cognito config
│       └── types/index.ts            # All TypeScript interfaces
│
└── backend/                          # AWS Serverless (Lambda + DynamoDB)
    ├── serverless.yml                # Infrastructure as Code (all AWS resources)
    ├── layers/shared/nodejs/
    │   └── utils.ts                  # Shared: DB client, response helpers, auth verify
    └── functions/
        ├── auth/handler.ts           # GET/PUT /auth/profile
        ├── movies/handler.ts         # GET /movies, /movies/{id}, /movies/search
        ├── theatres/handler.ts       # GET /theatres, /theatres/{id}
        ├── shows/handler.ts          # GET /shows
        ├── seats/
        │   ├── handler.ts            # GET/POST seats, lock/unlock (atomic TTL)
        │   └── websocket.ts          # WebSocket: real-time seat broadcasting
        ├── bookings/handler.ts       # POST/GET /bookings, cancel
        ├── payments/handler.ts       # Razorpay initiate + verify
        ├── bnpl/handler.ts           # BNPL status, book, pay, daily reminders
        ├── qrcode/handler.ts         # QR generation + S3 upload
        ├── chatbot/handler.ts        # AWS Lex + fulfillment handler
        └── notifications/handler.ts  # SES email + SNS SMS
```

---

## 🚀 Getting Started

### Prerequisites
- Node.js 20+
- Expo CLI: `npm install -g expo-cli`
- AWS CLI configured: `aws configure`
- Serverless Framework: `npm install -g serverless`

### Step 1 — Clone & Install
```bash
git clone https://github.com/your-org/cinecloud.git
cd cinecloud
npm run install:all
```

### Step 2 — Deploy Backend to AWS
```bash
cd backend
cp .env.example .env
# Edit .env if needed, then:
npx serverless deploy --stage dev

# After deploy, note the outputs:
# - UserPoolId   → EXPO_PUBLIC_COGNITO_USER_POOL_ID
# - UserPoolClientId → EXPO_PUBLIC_COGNITO_CLIENT_ID
# - ApiUrl       → EXPO_PUBLIC_API_URL
```

### Step 3 — Configure Frontend
```bash
cd frontend
cp .env.example .env
# Fill in values from Step 2 outputs
```

### Step 4 — Start the App
```bash
cd frontend
npx expo start
# Press 'a' for Android emulator, 'i' for iOS simulator
```

### Step 5 — Run Backend Locally (Optional)
```bash
cd backend
npx serverless offline start
# API available at http://localhost:3001
```

---

## 🗄️ DynamoDB Schema

### Users Table
| Field | Type | Description |
|-------|------|-------------|
| id (PK) | String | UUID |
| email | String | GSI |
| phone | String | GSI |
| name | String | Display name |
| gender | String | male/female/other — used for seat indicator |
| bnplLimit | Number | Default ₹2,000 |
| bnplUsed | Number | Current used credit |
| cognitoSub | String | Cognito user sub |

### Seats Table
| Field | Type | Description |
|-------|------|-------------|
| showId (PK) | String | Show ID |
| seatId (SK) | String | e.g. "A1", "G12" |
| status | String | AVAILABLE / HELD / BOOKED / UNAVAILABLE |
| category | String | SILVER / GOLD / PREMIUM / RECLINER |
| price | Number | Seat price in INR |
| heldBy | String | userId (during lock) |
| heldUntil | Number | Unix timestamp — **TTL field** (auto-expires) |
| bookedByGender | String | male/female — for gender indicator |

### BNPL Table
| Field | Type | Description |
|-------|------|-------------|
| id (PK) | String | UUID |
| userId | String | GSI |
| bookingId | String | Linked booking |
| amount | Number | Amount owed |
| dueDate | String | YYYY-MM-DD |
| status | String | PENDING / PAID / OVERDUE / PARTIAL |
| lateFee | Number | 2% per month if overdue |

---

## 🔐 Authentication Flow

1. User signs up with email + password via Cognito
2. Cognito sends OTP to email/phone
3. User confirms OTP → account verified
4. Login returns `accessToken`, `idToken`, `refreshToken`
5. Every API request includes `Authorization: Bearer <idToken>`
6. Lambda extracts userId from `requestContext.authorizer.claims.sub`

---

## 💺 Seat Locking Flow (Double-Booking Prevention)

```
User selects seats → POST /shows/{id}/seats/lock
     ↓
DynamoDB TransactWrite (atomic — all or nothing)
     ↓
Condition: status must be AVAILABLE
     ↓
If any seat taken → 409 Conflict → user told to reselect
     ↓
If all available → status = HELD, heldUntil = now + 300s
     ↓
DynamoDB TTL auto-clears after 5 minutes if not booked
     ↓
WebSocket broadcasts SEAT_HELD to all other users on this show
     ↓
User completes payment → status = BOOKED (permanent)
     ↓
WebSocket broadcasts SEAT_BOOKED with gender metadata
```

---

## 💳 BNPL Flow

1. User checks BNPL eligibility (GET /bnpl/status)
2. If eligible (credit available + no overdues) → see "Pay with BNPL" option
3. On booking confirmation → POST /bnpl/book creates BNPL record with due date
4. Booking is CONFIRMED immediately (no payment required now)
5. EventBridge runs daily Lambda → marks overdue, sends reminders
6. User pays via app → POST /bnpl/pay updates record to PAID/PARTIAL

---

## 🤖 Chatbot Setup (AWS Lex)

1. Go to AWS Console → Amazon Lex V2
2. Create Bot named `CineCloudBot`
3. Add Intents:
   - `BookTicket` — slots: Movie (AMAZON.Movie), Date (AMAZON.Date), City (AMAZON.City)
   - `ShowMovies` — sample utterances: "what's playing", "show movies", "now showing"
   - `MyBookings` — "my tickets", "booking history", "my bookings"
   - `Help` — "help", "what can you do"
   - `CancelBooking` — "cancel my ticket"
   - `BNPLInfo` — "what is BNPL", "book now pay later"
4. Set Lambda as fulfillment hook → `functions/chatbot/handler.lexFulfillment`
5. Copy Bot ID + Alias ID → set in backend `.env`

---

## 🧪 Testing

```bash
# Backend unit tests
cd backend && npm test

# Frontend component tests
cd frontend && npm test

# Integration test (local)
cd backend && npx serverless offline start
# Then run Postman collection from /docs/postman/
```

---

## 📦 Deployment

```bash
# Dev
cd backend && npx serverless deploy --stage dev

# Production
cd backend && npx serverless deploy --stage prod

# Frontend (EAS Build)
cd frontend && npx eas build --platform all --profile production
```

---

## 🛡️ Security Notes

- All Lambda functions verify JWT tokens via Cognito authorizer
- Seat gender info is stored but never exposed in list APIs — only shown visually (no name/personal data)
- DynamoDB TTL auto-expires seat locks — no cleanup Lambda needed
- S3 QR codes are public-read but contain only an opaque booking ID (no personal data in URL)
- BNPL credit decisions are server-side only — never trust client-sent credit amounts
