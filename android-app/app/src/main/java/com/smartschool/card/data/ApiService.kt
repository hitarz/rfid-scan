package com.smartschool.card.data

import com.smartschool.card.BuildConfig
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit

class ApiException(val code: Int, message: String) : Exception(message)

class ApiService {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    private val baseUrl = BuildConfig.SERVER_URL.trimEnd('/')

    fun authGoogle(idToken: String): AuthResponse {
        val body = JSONObject().put("id_token", idToken).toString()
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("$baseUrl/api/mobile/auth/google")
            .post(body)
            .build()
        return execute(request, AuthResponse::class.java)
    }

    fun getMe(token: String): MeResponse {
        val request = authorizedGet("$baseUrl/api/mobile/me", token)
        return execute(request, MeResponse::class.java)
    }


    fun createCard(token: String): CreateCardResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/mobile/card")
            .header("Authorization", "Bearer $token")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        return execute(request, CreateCardResponse::class.java)
    }




    fun startScanPrep(token: String): PrepStartResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/mobile/scan/prep")
            .header("Authorization", "Bearer $token")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        return execute(request, PrepStartResponse::class.java)
    }

    fun scanPrepStatus(token: String, prepId: String): PrepStatusResponse {
        val request = authorizedGet("$baseUrl/api/mobile/scan/prep/status/$prepId", token)
        return execute(request, PrepStatusResponse::class.java)
    }

    fun startBind(token: String): BindStartResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/mobile/card/bind/start")
            .header("Authorization", "Bearer $token")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        return execute(request, BindStartResponse::class.java)
    }

    fun bindStatus(token: String, bindId: String): BindStatusResponse {
        val request = authorizedGet("$baseUrl/api/mobile/card/bind/status/$bindId", token)
        return execute(request, BindStatusResponse::class.java)
    }

    fun resetCard(token: String): CreateCardResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/mobile/card/reset")
            .header("Authorization", "Bearer $token")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        return execute(request, CreateCardResponse::class.java)
    }

    fun logout(token: String) {
        val request = Request.Builder()
            .url("$baseUrl/api/mobile/logout")
            .header("Authorization", "Bearer $token")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        client.newCall(request).execute().use { /* ignore body */ }
    }

    private fun formatHttpError(code: Int, body: String): String {
        if (body.contains("<html", ignoreCase = true) || body.contains("<!doctype", ignoreCase = true)) {
            return when (code) {
                404 -> "Сервер застарілий або не перезапущений. Зупиніть server.py і запустіть знову на $baseUrl"
                401 -> "Сесія закінчилась. Увійдіть знову."
                else -> "Помилка сервера ($code). Перезапустіть server.py."
            }
        }
        return body.ifBlank { "HTTP $code" }
    }

    private fun authorizedGet(url: String, token: String): Request {
        return Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $token")
            .get()
            .build()
    }

    private fun <T> execute(request: Request, clazz: Class<T>): T {
        try {
            client.newCall(request).execute().use { response ->
                val body = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    val error = runCatching {
                        moshi.adapter(ErrorResponse::class.java).fromJson(body)?.error
                    }.getOrNull() ?: formatHttpError(response.code, body)
                    throw ApiException(response.code, error)
                }
                return try {
                    moshi.adapter(clazz).fromJson(body)
                        ?: throw ApiException(response.code, "Порожня відповідь сервера")
                } catch (e: Exception) {
                    throw ApiException(
                        response.code,
                        "Помилка розбору відповіді: ${e.message}",
                    )
                }
            }
        } catch (e: ApiException) {
            throw e
        } catch (e: UnknownHostException) {
            throw ApiException(0, "Сервер не знайдено: $baseUrl. Перевірте SERVER_URL і Wi‑Fi.")
        } catch (e: ConnectException) {
            throw ApiException(0, "Немає зʼєднання з сервером $baseUrl. Запустіть server.py.")
        } catch (e: SocketTimeoutException) {
            throw ApiException(0, "Таймаут зʼєднання з $baseUrl")
        } catch (e: IOException) {
            throw ApiException(0, "Мережева помилка: ${e.message ?: e.javaClass.simpleName}")
        }
    }
}
