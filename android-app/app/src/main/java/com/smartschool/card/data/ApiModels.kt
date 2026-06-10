package com.smartschool.card.data

data class AuthResponse(
    val token: String,
    val expires_at: String,
    val email: String,
    val display_name: String,
    val has_card: Boolean,
    val card_uid: String?,
    val class_group: String? = null,
)

data class MeResponse(
    val email: String,
    val display_name: String,
    val has_card: Boolean,
    val card_uid: String?,
    val class_group: String? = null,
)

data class CreateCardResponse(
    val card_uid: String,
    val display_name: String,
    val class_group: String? = null,
    val message: String,
)
data class PrepStartResponse(
    val prep_id: String,
    val card_uid: String,
    val expires_at: String,
    val instructions: String,
)

data class PrepStatusResponse(
    val status: String,
    val card_uid: String? = null,
    val hw_uid: String? = null,
    val error: String? = null,
)



data class BindStartResponse(
    val bind_id: String,
    val card_uid: String,
    val expires_at: String,
    val instructions: String,
)

data class BindStatusResponse(
    val status: String,
    val hw_uid: String? = null,
    val card_uid: String? = null,
    val error: String? = null,
)

data class ErrorResponse(
    val error: String,
)
