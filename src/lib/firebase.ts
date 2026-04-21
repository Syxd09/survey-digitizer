import { initializeApp } from 'firebase/app';
import { 
  getAuth, 
  GoogleAuthProvider, 
  signInWithPopup, 
  signInWithRedirect,
  getRedirectResult,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  browserPopupRedirectResolver 
} from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';
import firebaseConfig from '../../firebase-applet-config.json';

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app, firebaseConfig.firestoreDatabaseId);
export const auth = getAuth(app);
auth.useDeviceLanguage();

export const googleProvider = new GoogleAuthProvider();

// Handle redirect result on page load (for signInWithRedirect fallback)
getRedirectResult(auth).catch((err) => {
  console.warn('[AUTH] Redirect result check:', err.code || err.message);
});

export const signIn = async () => {
  try {
    return await signInWithPopup(auth, googleProvider);
  } catch (error: any) {
    console.error('[AUTH] Sign-in failed:', error.code, error.message);
    
    if (error.code === 'auth/unauthorized-domain') {
      try {
        return await signInWithRedirect(auth, googleProvider);
      } catch (redirectError: any) {
        console.error('[AUTH] Redirect also failed:', redirectError.code);
      }
      throw new Error(
        'This domain (localhost) is not authorized in the Firebase project. ' +
        'Go to Firebase Console → Authentication → Settings → Authorized domains → Add "localhost".'
      );
    }
    
    if (error.code === 'auth/popup-blocked') {
      throw new Error('Popup was blocked by the browser. Please allow popups for this site.');
    }
    
    throw error;
  }
};

export const signUpWithEmail = (email: string, pass: string) => 
  createUserWithEmailAndPassword(auth, email, pass);

export const signInWithEmail = (email: string, pass: string) => 
  signInWithEmailAndPassword(auth, email, pass);

export const signOut = () => auth.signOut();
