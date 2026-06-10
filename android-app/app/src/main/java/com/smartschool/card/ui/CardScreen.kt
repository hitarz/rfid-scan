package com.smartschool.card.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Nfc
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CardScreen(
    state: UiState,
    onCreateCard: () -> Unit,
    onStartPass: () -> Unit,
    onLogout: () -> Unit,
) {
    val classUnassigned = state.classGroup.isNullOrBlank() ||
        state.classGroup == AppViewModel.CLASS_UNASSIGNED

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = "Вітаємо, ${state.displayName}",
            fontSize = 20.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = state.email,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (state.cardUid != null) {
            DigitalCard(
                uid = state.cardUid,
                name = state.displayName,
                classGroup = if (classUnassigned) null else state.classGroup,
            )
            Text(
                text = "Щоб пройти, прикладіть телефон до зчитувача. Якщо ваш телефон погано сканується, натисніть кнопку нижче (потрібен інтернет).",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 8.dp),
            )
            val passInProgress = state.passStatus == "waiting"
            Button(
                onClick = onStartPass,
                enabled = !state.isLoading && !passInProgress,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (passInProgress) {
                    CircularProgressIndicator(modifier = Modifier.height(20.dp))
                    Text("  Очікування сканування…", modifier = Modifier.padding(start = 8.dp))
                } else {
                    Icon(Icons.Default.Nfc, contentDescription = null)
                    Text("  Пройти (через сервер)", modifier = Modifier.padding(start = 4.dp))
                }
            }

        } else {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("У вас ще немає картки")
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "Створіть картку для роботи системи (потрібен інтернет один раз).",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Button(
                onClick = onCreateCard,
                enabled = !state.isLoading,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (state.isLoading) {
                    CircularProgressIndicator(modifier = Modifier.height(20.dp))
                } else {
                    Text("Створити картку")
                }
            }
        }

        Spacer(modifier = Modifier.weight(1f))

        OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) {
            Text("Вийти")
        }
    }
}


@Composable
private fun DigitalCard(uid: String, name: String, classGroup: String?) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(200.dp)
            .background(
                brush = Brush.linearGradient(
                    colors = listOf(Color(0xFF2563EB), Color(0xFF1D4ED8)),
                ),
                shape = RoundedCornerShape(20.dp),
            )
            .padding(24.dp),
    ) {
        Column(modifier = Modifier.align(Alignment.BottomStart)) {
            Text("SMART SCHOOL", color = Color.White.copy(alpha = 0.8f), fontSize = 12.sp)
            Spacer(modifier = Modifier.height(8.dp))
            Text(name, color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            if (!classGroup.isNullOrBlank()) {
                Text(classGroup, color = Color.White.copy(alpha = 0.85f), fontSize = 14.sp)
            }
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = uid,
                color = Color.White,
                fontFamily = FontFamily.Monospace,
                fontSize = 18.sp,
                letterSpacing = 2.sp,
            )
        }
        Icon(
            Icons.Default.Nfc,
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.5f),
            modifier = Modifier.align(Alignment.TopEnd),
        )
    }
}
