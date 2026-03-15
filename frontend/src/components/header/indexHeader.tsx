import React from "react";
import { View, TouchableOpacity, Image } from "react-native";
import { MaterialIcons } from "@expo/vector-icons";
import { styles } from "@/styles/styleHeader"
import { colors } from "@/styles/Colors";
import { useRouter } from "expo-router";

// importe o logo do app:
import FastLogo from "../../../assets/images/fast_Logo.png";

interface HeaderProps {
  leftIconName?: "logout" | "arrow-back" | "menu" | null;
  onLeftIconPress?: () => void;
}

export function Header({ leftIconName, onLeftIconPress }: HeaderProps) {
  const router = useRouter();

  const handlePress =
    onLeftIconPress ||
    (() => {
      if (leftIconName === "arrow-back") router.back();
    });

  const leftIcon =
    leftIconName ? (
      <TouchableOpacity onPress={handlePress} style={styles.actionIconContainer}>
        <MaterialIcons name={leftIconName} size={28} color={colors.action.text} />
      </TouchableOpacity>
    ) : (
      <View style={styles.actionIconContainer} />
    );

  return (
    <View style={styles.container}>
      {leftIcon}

      <View style={styles.logoContainer}>
        <Image source={FastLogo} style={styles.logo} resizeMode="contain" />
      </View>
    </View>
  );
}
