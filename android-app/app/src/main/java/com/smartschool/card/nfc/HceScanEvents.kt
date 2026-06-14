package com.smartschool.card.nfc

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/**
 * Синглтон для передачі подій "HCE успішно відповів на сканування"
 * від CardEmulationService → AppViewModel без deprecated LocalBroadcastManager
 */
object HceScanEvents {
    private val _flow = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val flow: SharedFlow<String> = _flow.asSharedFlow()

    fun emit(cardUid: String) {
        _flow.tryEmit(cardUid)
    }
}
