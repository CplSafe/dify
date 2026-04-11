import type { Var } from '../../types'
import type { Authorization, Body, HttpNodeType, Method, Timeout } from './types'
import { useBoolean } from 'ahooks'
import { produce } from 'immer'
import { useCallback, useEffect, useState } from 'react'
import {
  useNodesReadOnly,
} from '@/app/components/workflow/hooks'
import useNodeCrud from '@/app/components/workflow/nodes/_base/hooks/use-node-crud'
import { useStore } from '../../store'
import { VarType } from '../../types'
import useVarList from '../_base/hooks/use-var-list'
import useKeyValueList from './hooks/use-key-value-list'
import { BodyType } from './types'
import { transformToBodyPayload } from './utils'

const useConfig = (id: string, payload: HttpNodeType) => {
  const { nodesReadOnly: readOnly } = useNodesReadOnly()

  const defaultConfig = useStore(s => s.nodesDefaultConfigs?.[payload.type])

  const { inputs, setInputs } = useNodeCrud<HttpNodeType>(id, payload)

  const { handleVarListChange, handleAddVariable } = useVarList<HttpNodeType>({
    inputs,
    setInputs,
  })

  const [isDataReady, setIsDataReady] = useState(false)

  useEffect(() => {
    const isReady = defaultConfig && Object.keys(defaultConfig).length > 0
    if (isReady) {
      const newInputs = {
        ...defaultConfig,
        ...inputs,
      }
      const bodyData = newInputs.body.data
      if (typeof bodyData === 'string') {
        newInputs.body = {
          ...newInputs.body,
          data: transformToBodyPayload(bodyData, [BodyType.formData, BodyType.xWwwFormUrlencoded].includes(newInputs.body.type)),
        }
      }
      else if (!bodyData) {
        newInputs.body = {
          ...newInputs.body,
          data: [],
        }
      }

      setInputs(newInputs)
      setIsDataReady(true)
    }
  }, [defaultConfig])

  const updateInputs = useCallback(<K extends keyof HttpNodeType>(field: K, value: HttpNodeType[K]) => {
    setInputs(produce(inputs, (draft) => {
      draft[field] = value
    }))
  }, [inputs, setInputs])

  const handleFieldChange = useCallback((field: string) => {
    return (value: string) => {
      setInputs(produce(inputs, (draft) => {
        (draft as any)[field] = value
      }))
    }
  }, [inputs, setInputs])

  const {
    list: headers,
    setList: setHeaders,
    addItem: addHeader,
    isKeyValueEdit: isHeaderKeyValueEdit,
    toggleIsKeyValueEdit: toggleIsHeaderKeyValueEdit,
  } = useKeyValueList(inputs.headers, handleFieldChange('headers'))

  const {
    list: params,
    setList: setParams,
    addItem: addParam,
    isKeyValueEdit: isParamKeyValueEdit,
    toggleIsKeyValueEdit: toggleIsParamKeyValueEdit,
  } = useKeyValueList(inputs.params, handleFieldChange('params'))

  // authorization
  const [isShowAuthorization, {
    setTrue: showAuthorization,
    setFalse: hideAuthorization,
  }] = useBoolean(false)

  // curl import panel
  const [isShowCurlPanel, {
    setTrue: showCurlPanel,
    setFalse: hideCurlPanel,
  }] = useBoolean(false)

  const handleCurlImport = useCallback((newNode: HttpNodeType) => {
    setInputs(produce(inputs, (draft) => {
      draft.method = newNode.method
      draft.url = newNode.url
      draft.headers = newNode.headers
      draft.params = newNode.params
      draft.body = newNode.body
    }))
  }, [inputs, setInputs])

  const filterVar = useCallback((varPayload: Var) => {
    return [VarType.string, VarType.number, VarType.secret].includes(varPayload.type)
  }, [])

  return {
    readOnly,
    isDataReady,
    inputs,
    handleVarListChange,
    handleAddVariable,
    filterVar,
    handleMethodChange: useCallback((method: Method) => updateInputs('method', method), [updateInputs]),
    handleUrlChange: useCallback((url: string) => updateInputs('url', url), [updateInputs]),
    // headers
    headers,
    setHeaders,
    addHeader,
    isHeaderKeyValueEdit,
    toggleIsHeaderKeyValueEdit,
    // params
    params,
    setParams,
    addParam,
    isParamKeyValueEdit,
    toggleIsParamKeyValueEdit,
    // body
    setBody: useCallback((data: Body) => updateInputs('body', data), [updateInputs]),
    // ssl verify
    handleSSLVerifyChange: useCallback((checked: boolean) => updateInputs('ssl_verify', checked), [updateInputs]),
    // authorization
    isShowAuthorization,
    showAuthorization,
    hideAuthorization,
    setAuthorization: useCallback((authorization: Authorization) => updateInputs('authorization', authorization), [updateInputs]),
    setTimeout: useCallback((timeout: Timeout) => updateInputs('timeout', timeout), [updateInputs]),
    // curl import
    isShowCurlPanel,
    showCurlPanel,
    hideCurlPanel,
    handleCurlImport,
    handleTokenFieldNameChange: useCallback((name: string) => updateInputs('token_field_name', name || undefined), [updateInputs]),
    handleHttpBillingPriceChange: useCallback((price: number | undefined) => updateInputs('billing_price_per_k_tokens', price), [updateInputs]),
  }
}

export default useConfig
