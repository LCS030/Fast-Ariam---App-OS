// src/utils/storage.ts
import AsyncStorage from "@react-native-async-storage/async-storage";

export async function storageSet(key: string, value: any): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    console.log("❌ STORAGE SET ERROR:", err);
  }
}

export async function storageGet(key: string): Promise<any | null> {
  try {
    const json = await AsyncStorage.getItem(key);
    return json ? JSON.parse(json) : null;
  } catch (err) {
    console.log("❌ STORAGE GET ERROR:", err);
    return null;
  }
}

export async function storageRemove(key: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(key);
  } catch (err) {
    console.log("❌ STORAGE REMOVE ERROR:", err);
  }
}

export async function setToken(token: string, access_token?: any): Promise<void> {
  // keep signature flexible, but store raw token
  try {
    await AsyncStorage.setItem("token", token);
  } catch (err) {
    console.log("❌ SET TOKEN ERROR:", err);
  }
}

export async function getToken(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem("token");
  } catch (err) {
    console.log("❌ GET TOKEN ERROR:", err);
    return null;
  }
}

export async function removeToken(): Promise<void> {
  try {
    await AsyncStorage.removeItem("token");
  } catch (err) {
    console.log("❌ REMOVE TOKEN ERROR:", err);
  }
}