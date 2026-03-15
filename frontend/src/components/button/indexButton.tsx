import { TouchableOpacity, Text, ActivityIndicator, ViewStyle } from "react-native";
import { styles } from "@/styles/styleButton";
import { colors } from "@/styles/Colors";

interface Props {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: "primary" | "secondary";

  // novos
  fontSize?: number;
    width?: ViewStyle["width"]
    height?: ViewStyle["height"]
}

export function Button({
  title,
  onPress,
  loading,
  disabled,
  variant = "primary",
  fontSize,
  width,
  height,
}: Props) {
  const styleBtn = variant === "primary" ? styles.primaryBtn : styles.secondaryBtn;
  const styleText = variant === "primary" ? styles.primaryText : styles.secondaryText;

  return (
    <TouchableOpacity
      style={[
        styleBtn,
        width ? { width } : {},
        height ? { height, justifyContent: "center" } : {},
        disabled && { opacity: 0.5 },
      ]}
      onPress={onPress}
      disabled={disabled || loading}
      activeOpacity={0.8}
    >
      {loading ? (
        <ActivityIndicator color={colors.action.text} />
      ) : (
        <Text style={[styleText, fontSize ? { fontSize } : {}]}>{title}</Text>
      )}
    </TouchableOpacity>
  );
}
