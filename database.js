import React, { useState, useEffect } from 'react';
import { initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously, signInWithCustomToken, onAuthStateChanged } from 'firebase/auth';
import { getFirestore, collection, addDoc, onSnapshot, query, orderBy, serverTimestamp } from 'firebase/firestore';

function App() {
  const [db, setDb] = useState(null);
  const [auth, setAuth] = useState(null);
  const [userId, setUserId] = useState(null);
  const [isAuthReady, setIsAuthReady] = useState(false);
  const [items, setItems] = useState([]);
  const [date, setDate] = useState('');
  const [itemName, setItemName] = useState('');
  const [itemSize, setItemSize] = useState('');
  const [quantity, setQuantity] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Initialize Firebase and set up authentication listener
  useEffect(() => {
    try {
      const appId = typeof __app_id !== 'undefined' ? __app_id : 'default-app-id';
      const firebaseConfig = JSON.parse(typeof __firebase_config !== 'undefined' ? __firebase_config : '{}');

      if (Object.keys(firebaseConfig).length === 0) {
        throw new Error("Firebase config is not defined. Cannot initialize Firebase.");
      }

      const app = initializeApp(firebaseConfig);
      const firestore = getFirestore(app);
      const authentication = getAuth(app);

      setDb(firestore);
      setAuth(authentication);

      const unsubscribe = onAuthStateChanged(authentication, async (user) => {
        if (user) {
          setUserId(user.uid);
          setIsAuthReady(true);
        } else {
          try {
            // Sign in anonymously if no user is authenticated
            if (typeof __initial_auth_token !== 'undefined' && __initial_auth_token) {
                await signInWithCustomToken(authentication, __initial_auth_token);
            } else {
                await signInAnonymously(authentication);
            }
          } catch (authError) {
            console.error("Firebase Auth Error:", authError);
            setError(`Authentication failed: ${authError.message}`);
          }
        }
        setLoading(false);
      });

      return () => unsubscribe();
    } catch (err) {
      console.error("Firebase Initialization Error:", err);
      setError(`Failed to initialize Firebase: ${err.message}`);
      setLoading(false);
    }
  }, []);

  // Fetch data from Firestore once authentication is ready
  useEffect(() => {
    if (db && userId && isAuthReady) {
      const collectionPath = `artifacts/${__app_id}/public/data/inventoryItems`;
      const q = query(collection(db, collectionPath));

      const unsubscribe = onSnapshot(q, (snapshot) => {
        const itemsData = snapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        }));
        // Sort items by timestamp in descending order for display
        itemsData.sort((a, b) => (b.timestamp?.toDate() || 0) - (a.timestamp?.toDate() || 0));
        setItems(itemsData);
      }, (err) => {
        console.error("Firestore Snapshot Error:", err);
        setError(`Failed to fetch items: ${err.message}`);
      });

      return () => unsubscribe();
    }
  }, [db, userId, isAuthReady]);

  const handleAddItem = async () => {
    if (!itemName || !itemSize || !quantity || !date) {
      setError("All fields are required.");
      return;
    }
    if (!db) {
      setError("Database not initialized.");
      return;
    }

    setLoading(true);
    setError('');
    try {
      const collectionPath = `artifacts/${__app_id}/public/data/inventoryItems`;
      await addDoc(collection(db, collectionPath), {
        date: date,
        item: itemName,
        itemSize: itemSize,
        quantity: parseInt(quantity, 10), // Ensure quantity is stored as a number
        timestamp: serverTimestamp(), // Add a timestamp for ordering
        addedBy: userId, // Store which user added the item
      });
      setDate('');
      setItemName('');
      setItemSize('');
      setQuantity('');
    } catch (e) {
      console.error("Error adding document: ", e);
      setError(`Failed to add item: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="text-lg font-semibold text-gray-700">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-4 sm:p-6 font-sans">
      <div className="max-w-4xl mx-auto bg-white rounded-xl shadow-lg p-6 sm:p-8">
        <h1 className="text-3xl sm:text-4xl font-extrabold text-center text-gray-800 mb-8">
          Inventory Management
        </h1>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-md relative mb-6" role="alert">
            <strong className="font-bold">Error:</strong>
            <span className="block sm:inline"> {error}</span>
          </div>
        )}

        <div className="mb-8 p-6 bg-blue-50 rounded-lg shadow-inner">
          <h2 className="text-2xl font-bold text-gray-700 mb-4">Add New Item</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label htmlFor="date" className="block text-sm font-medium text-gray-700 mb-1">Date</label>
              <input
                type="date"
                id="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label htmlFor="itemName" className="block text-sm font-medium text-gray-700 mb-1">Item Name</label>
              <input
                type="text"
                id="itemName"
                value={itemName}
                onChange={(e) => setItemName(e.target.value)}
                placeholder="e.g., Apple"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label htmlFor="itemSize" className="block text-sm font-medium text-gray-700 mb-1">Item Size</label>
              <input
                type="text"
                id="itemSize"
                value={itemSize}
                onChange={(e) => setItemSize(e.target.value)}
                placeholder="e.g., Large, 1.75L"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label htmlFor="quantity" className="block text-sm font-medium text-gray-700 mb-1">Quantity</label>
              <input
                type="number"
                id="quantity"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="e.g., 10"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
          </div>
          <button
            onClick={handleAddItem}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-md shadow-md transition duration-300 ease-in-out transform hover:scale-105"
            disabled={loading}
          >
            {loading ? 'Adding...' : 'Add Item'}
          </button>
        </div>

        <div className="mb-8">
          <h2 className="text-2xl font-bold text-gray-700 mb-4">Current Inventory</h2>
          {items.length === 0 ? (
            <p className="text-gray-600 text-center">No items in inventory. Add some above!</p>
          ) : (
            <div className="overflow-x-auto rounded-lg shadow-md">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Date
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Item
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Size
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Quantity
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Added By
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {items.map((item) => (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {item.date}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {item.item}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {item.itemSize}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {item.quantity}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 truncate max-w-xs">
                        {item.addedBy}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {userId && (
          <div className="text-sm text-gray-500 text-center mt-6 p-3 bg-gray-50 rounded-lg shadow-sm">
            Your User ID: <span className="font-mono text-gray-700 break-all">{userId}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
