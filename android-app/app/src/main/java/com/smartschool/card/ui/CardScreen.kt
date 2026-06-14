package com.smartschool.card.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Nfc
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun CardScreen(
    state: UiState,
    onCreateCard: () -> Unit,
    onLogout: () -> Unit,
) {
    val classUnassigned = state.classGroup.isNullOrBlank() ||
        state.classGroup == AppViewModel.CLASS_UNASSIGNED

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // Заголовок
        Text(
            text = "Smart School",
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.primary,
            letterSpacing = 1.5.sp,
        )
        Text(
            text = state.displayName,
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = state.email,
            fontSize = 13.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(modifier = Modifier.height(4.dp))

        if (state.cardUid != null) {
            // Цифрова картка
            DigitalCard(
                uid = state.cardUid,
                name = state.displayName,
                classGroup = if (classUnassigned) null else state.classGroup,
            )

            // NFC статус
            NfcStatusBanner(lastScanTime = state.lastScanTime)

            // Інструкція
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                ),
                shape = RoundedCornerShape(16.dp),
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        Icons.Default.Nfc,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(28.dp),
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Text(
                        text = "Прикладіть телефон до зчитувача. Інтернет на телефоні не потрібен — картка працює офлайн.",
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        lineHeight = 18.sp,
                    )
                }
            }
        } else {
            // Немає картки
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
                ),
                shape = RoundedCornerShape(16.dp),
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = "Картки немає",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "Створіть цифрову картку. Потрібен інтернет лише один раз.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp,
                    )
                }
            }

            Button(
                onClick = onCreateCard,
                enabled = !state.isLoading,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
            ) {
                Text(
                    text = if (state.isLoading) "Створення…" else "Створити картку",
                    modifier = Modifier.padding(vertical = 4.dp),
                )
            }
        }

        Spacer(modifier = Modifier.weight(1f))

        OutlinedButton(
            onClick = onLogout,
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
        ) {
            Text("Вийти")
        }
    }
}

@Composable
private fun NfcStatusBanner(lastScanTime: String?) {
    val infiniteTransition = rememberInfiniteTransition(label = "nfc_pulse")
    val pulse by infiniteTransition.animateFloat(
        initialValue = 0.7f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulse",
    )

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (lastScanTime != null)
                Color(0xFF166534).copy(alpha = 0.1f)
            else
                Color(0xFF1E40AF).copy(alpha = 0.08f)
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (lastScanTime != null) {
                Icon(
                    Icons.Default.CheckCircle,
                    contentDescription = null,
                    tint = Color(0xFF16A34A),
                    modifier = Modifier.size(22.dp),
                )
                Column {
                    Text(
                        text = "✅ Прохід зафіксовано",
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
                        color = Color(0xFF15803D),
                    )
                    Text(
                        text = "Сканування о $lastScanTime",
                        fontSize = 12.sp,
                        color = Color(0xFF166534).copy(alpha = 0.8f),
                    )
                }
            } else {
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .scale(pulse)
                        .background(Color(0xFF2563EB), CircleShape),
                )
                Text(
                    text = "NFC активно — прикладіть до зчитувача",
                    fontSize = 13.sp,
                    color = Color(0xFF1E40AF),
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}

@Composable
private fun DigitalCard(uid: String, name: String, classGroup: String?) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(210.dp)
            .background(
                brush = Brush.linearGradient(
                    colors = listOf(Color(0xFF1E3A8A), Color(0xFF2563EB), Color(0xFF3B82F6)),
                ),
                shape = RoundedCornerShape(24.dp),
            )
            .padding(24.dp),
    ) {
        // Декоративне коло
        Box(
            modifier = Modifier
                .size(160.dp)
                .align(Alignment.TopEnd)
                .alpha(0.1f)
                .background(Color.White, CircleShape),
        )

        Column(modifier = Modifier.align(Alignment.BottomStart)) {
            Text(
                text = "SMART SCHOOL",
                color = Color.White.copy(alpha = 0.6f),
                fontSize = 10.sp,
                letterSpacing = 2.sp,
                fontWeight = FontWeight.Medium,
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = name,
                color = Color.White,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
            )
            if (!classGroup.isNullOrBlank()) {
                Text(
                    text = "Клас $classGroup",
                    color = Color.White.copy(alpha = 0.75f),
                    fontSize = 13.sp,
                )
            }
            Spacer(modifier = Modifier.height(14.dp))
            Text(
                text = uid.chunked(2).joinToString(" "),
                color = Color.White,
                fontFamily = FontFamily.Monospace,
                fontSize = 16.sp,
                letterSpacing = 1.sp,
            )
        }

        Icon(
            Icons.Default.Nfc,
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.4f),
            modifier = Modifier
                .align(Alignment.TopEnd)
                .size(36.dp),
        )
    }
}
