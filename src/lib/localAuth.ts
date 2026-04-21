/**
 * Local Authentication Module
 * Replaces Firebase Auth with localStorage-based user management.
 */

export interface LocalUser {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
  emailVerified: boolean;
  isAnonymous: boolean;
  tenantId: string | null;
  providerData: {
    providerId: string;
    displayName: string | null;
    email: string | null;
    photoURL: string | null;
  }[];
}

const STORAGE_KEY = 'survey_digitizer_user';
const USERS_KEY = 'survey_digitizer_users';

let currentUser: LocalUser | null = null;
let authListeners: ((user: LocalUser | null) => void)[] = [];

function generateUID(): string {
  return 'local-' + crypto.randomUUID();
}

function notifyListeners() {
  authListeners.forEach(cb => cb(currentUser));
}

function loadUser(): LocalUser | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {}
  return null;
}

function saveUser(user: LocalUser | null) {
  if (user) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function getRegisteredUsers(): Record<string, { email: string; password: string; uid: string; displayName: string }> {
  try {
    const stored = localStorage.getItem(USERS_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return {};
}

function saveRegisteredUsers(users: Record<string, any>) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

// Initialize: load persisted session
currentUser = loadUser();

/**
 * Listen for auth state changes (mimics Firebase onAuthStateChanged)
 */
export function onAuthStateChanged(callback: (user: LocalUser | null) => void): () => void {
  authListeners.push(callback);
  // Fire immediately with current state
  setTimeout(() => callback(currentUser), 0);
  return () => {
    authListeners = authListeners.filter(cb => cb !== callback);
  };
}

/**
 * Sign up with email and password
 */
export function signUpWithEmail(email: string, password: string): LocalUser {
  const users = getRegisteredUsers();
  if (users[email]) {
    throw new Error('An account with this email already exists.');
  }

  const uid = generateUID();
  const displayName = email.split('@')[0];

  users[email] = { email, password, uid, displayName };
  saveRegisteredUsers(users);

  const user: LocalUser = {
    uid,
    email,
    displayName,
    photoURL: null,
    emailVerified: true,
    isAnonymous: false,
    tenantId: null,
    providerData: [{ providerId: 'local', displayName, email, photoURL: null }]
  };

  currentUser = user;
  saveUser(user);
  notifyListeners();
  return user;
}

/**
 * Sign in with email and password
 */
export function signInWithEmail(email: string, password: string): LocalUser {
  const users = getRegisteredUsers();
  const record = users[email];

  if (!record) {
    throw new Error('No account found with this email. Please sign up first.');
  }
  if (record.password !== password) {
    throw new Error('Incorrect password. Please try again.');
  }

  const user: LocalUser = {
    uid: record.uid,
    email: record.email,
    displayName: record.displayName,
    photoURL: null,
    emailVerified: true,
    isAnonymous: false,
    tenantId: null,
    providerData: [{ providerId: 'local', displayName: record.displayName, email: record.email, photoURL: null }]
  };

  currentUser = user;
  saveUser(user);
  notifyListeners();
  return user;
}

/**
 * Sign out
 */
export function signOut() {
  currentUser = null;
  saveUser(null);
  notifyListeners();
}

/**
 * Get the current user (synchronous)
 */
export function getCurrentUser(): LocalUser | null {
  return currentUser;
}
